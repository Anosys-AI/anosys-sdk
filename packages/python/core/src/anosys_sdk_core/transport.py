"""
Size-limited delivery to AnoSys ingestion.

AnoSys ingestion drops any request body above 10 MB. Every package that
posts to AnoSys goes through these helpers so that:

- each request body stays under ``ANOSYS_MAX_BATCH_BYTES`` (default 10,000,000),
  measured on the final JSON (after encryption);
- a record that is too big on its own has its largest content fields
  truncated (``cvs199`` raw first), each marked with its original size, and
  is dropped with one warning if it still does not fit;
- failures are classified: 400/401/403/404/413/422 are permanent and the
  records are dropped, timeouts, connection errors, 408, 429 and 5xx are
  retried through a bounded ``PendingQueue``;
- a 401/403 pauses collection for a while instead of queueing more data.
"""

import json
import logging
import os
import stat
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_MAX_BATCH_BYTES = 10_000_000
# Headroom below the limit for headers and proxies
_TARGET_RATIO = 0.95

PERMANENT_STATUS = {400, 401, 403, 404, 413, 422}
PAUSE_STATUS = {401, 403}
# Content fields truncated first when a single record is too large
TRUNCATE_FIRST = ("cvs199", "raw", "tool_use_result", "cvs26", "file_states")
TRUNCATION_MARK = "...[truncated: original {size} bytes]"


def max_batch_bytes() -> int:
    """Request-body limit from ANOSYS_MAX_BATCH_BYTES (default 10,000,000)."""
    try:
        value = int(os.environ.get("ANOSYS_MAX_BATCH_BYTES", DEFAULT_MAX_BATCH_BYTES))
        return value if value > 1024 else DEFAULT_MAX_BATCH_BYTES
    except (TypeError, ValueError):
        return DEFAULT_MAX_BATCH_BYTES


def _target(limit: Optional[int]) -> int:
    return int((limit or max_batch_bytes()) * _TARGET_RATIO)


def json_size(value: Any) -> int:
    """Size in bytes of ``value`` serialized the way it is posted."""
    return len(json.dumps(value, separators=(",", ":"), default=str).encode("utf-8"))


# ── single record ─────────────────────────────────────────────────────────────

def _is_encrypted(value: str) -> bool:
    return value.startswith("enc2:") or value.startswith('"enc2:')


def fit_record(record: Dict[str, Any], limit: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """
    Return ``record`` if it fits in one request, a truncated copy if
    truncating its largest string fields makes it fit, or None (logged once).
    """
    target = _target(limit)
    size = json_size([record])
    if size <= target:
        return record

    result = dict(record)
    order = [k for k in TRUNCATE_FIRST if isinstance(result.get(k), str)]
    order += sorted(
        (k for k, v in result.items() if isinstance(v, str) and k not in order),
        key=lambda k: len(result[k]),
        reverse=True,
    )
    for key in order:
        excess = json_size([result]) - target
        if excess <= 0:
            break
        value = result[key]
        original = len(value.encode("utf-8"))
        mark = TRUNCATION_MARK.format(size=original)
        if _is_encrypted(value):
            # a cut ciphertext cannot be decrypted: replace the whole value
            result[key] = mark.lstrip(".")
            continue
        keep = max(0, len(value) - excess - len(mark) - 64)
        result[key] = value[:keep] + mark
    if json_size([result]) <= target:
        logger.warning("Record over the %d-byte limit was truncated", target)
        return result
    logger.warning("Dropped a record that does not fit in %d bytes even after truncation", target)
    return None


def chunk_records(records: List[Dict[str, Any]], limit: Optional[int] = None) -> List[List[Dict[str, Any]]]:
    """Split records into request bodies under the byte limit (oversized ones fitted or dropped)."""
    target = _target(limit)
    chunks: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []
    current_size = 2  # "[]"
    for record in records:
        fitted = fit_record(record, limit)
        if fitted is None:
            continue
        size = json_size(fitted) + 1  # comma
        if current and current_size + size > target:
            chunks.append(current)
            current, current_size = [], 2
        current.append(fitted)
        current_size += size
    if current:
        chunks.append(current)
    return chunks


def post_record(url: str, record: Dict[str, Any], timeout: float = 5,
                headers: Optional[Dict[str, str]] = None, post: Optional[Callable] = None):
    """
    POST one already-encrypted record, fitted under the size limit. Returns
    the response, or None when the record had to be dropped. Used by the
    application SDKs, which send one span or call per request.
    """
    fitted = fit_record(record)
    if fitted is None:
        return None
    if post is None:
        import requests
        post = requests.post
    return post(url, json=fitted, timeout=timeout, headers=headers)


# ── failure classification ────────────────────────────────────────────────────

def is_permanent(status: Optional[int]) -> bool:
    """True for responses that will never succeed on retry."""
    return status in PERMANENT_STATUS


def send_records(
    url: str,
    records: List[Dict[str, Any]],
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 15,
    limit: Optional[int] = None,
    post: Optional[Callable[..., Any]] = None,
) -> Tuple[int, List[Dict[str, Any]], Optional[int]]:
    """
    POST records in size-limited batches.

    Returns:
        (sent, retryable, pause_status): the number of records accepted, the
        records worth retrying later, and the status code (401/403) that
        should pause collection, if any. Permanently rejected records are
        dropped and logged.
    """
    if post is None:
        import requests
        post = requests.post
    sent = 0
    retryable: List[Dict[str, Any]] = []
    pause: Optional[int] = None
    for chunk in chunk_records(records, limit):
        if pause is not None:
            break  # the key is rejected; don't send (or queue) the rest
        try:
            response = post(url, json=chunk, headers=headers or {}, timeout=timeout)
            status = getattr(response, "status_code", 200)
        except Exception as e:  # timeout, connection error
            logger.warning("Ingestion unreachable (%s); %d record(s) kept for retry", type(e).__name__, len(chunk))
            retryable.extend(chunk)
            continue
        if status < 300:
            sent += len(chunk)
        elif is_permanent(status):
            logger.warning("Ingestion rejected %d record(s) with %d; dropped", len(chunk), status)
            if status in PAUSE_STATUS:
                pause = status
        else:
            logger.warning("Ingestion returned %d; %d record(s) kept for retry", status, len(chunk))
            retryable.extend(chunk)
    return sent, retryable, pause


# ── pause marker ──────────────────────────────────────────────────────────────

def pause_collection(marker: Path, status: int, seconds: int = 6 * 3600) -> None:
    """Stop building payloads for ``seconds`` after a 401/403."""
    try:
        _write_private(marker, json.dumps({"until": time.time() + seconds, "status": status}))
    except Exception as e:
        logger.debug("Could not write pause marker: %s", e)


def is_paused(marker: Path) -> bool:
    """True while a pause marker is active."""
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
        if time.time() < float(data.get("until", 0)):
            return True
        marker.unlink()
    except Exception:
        pass
    return False


# ── bounded retry queue ───────────────────────────────────────────────────────

def _write_private(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(content)
    os.replace(tmp, path)


class PendingQueue:
    """
    Records waiting for a retry, kept in a 0600 JSONL file and bounded by
    total size, age and attempts. Oldest entries are dropped first.
    """

    def __init__(
        self,
        path: Path,
        max_bytes: int = 50_000_000,
        max_age_seconds: int = 24 * 3600,
        max_attempts: int = 5,
    ):
        self.path = Path(path)
        self.max_bytes = max_bytes
        self.max_age_seconds = max_age_seconds
        self.max_attempts = max_attempts

    def load(self) -> List[Dict[str, Any]]:
        """Entries still eligible for retry: {"record", "first_failed", "attempts"}."""
        entries: List[Dict[str, Any]] = []
        if not self.path.is_file():
            return entries
        now = time.time()
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if "record" not in entry:  # pre-v2 file: a bare record per line
                        continue
                    if now - float(entry.get("first_failed", now)) > self.max_age_seconds:
                        continue
                    if int(entry.get("attempts", 0)) >= self.max_attempts:
                        continue
                    entries.append(entry)
        except Exception as e:
            logger.warning("Could not read pending queue: %s", e)
        return entries

    def save(self, entries: List[Dict[str, Any]]) -> None:
        """Replace the queue with ``entries`` (newest kept within max_bytes)."""
        lines: List[str] = []
        total = 0
        for entry in reversed(entries):
            line = json.dumps(entry, separators=(",", ":"), default=str)
            if total + len(line) + 1 > self.max_bytes:
                break
            lines.append(line)
            total += len(line) + 1
        lines.reverse()
        if not lines:
            self.clear()
            return
        try:
            _write_private(self.path, "\n".join(lines) + "\n")
        except Exception as e:
            logger.warning("Could not save pending queue: %s", e)

    def clear(self) -> None:
        try:
            if self.path.exists():
                self.path.unlink()
        except Exception as e:
            logger.warning("Could not clear pending queue: %s", e)

    @staticmethod
    def entries_for(records: List[Dict[str, Any]], previous: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        now = time.time()
        return [
            {
                "record": r,
                "first_failed": (previous or {}).get("first_failed", now),
                "attempts": int((previous or {}).get("attempts", 0)) + 1,
            }
            for r in records
        ]


def deliver(
    url: str,
    records: List[Dict[str, Any]],
    queue: PendingQueue,
    pause_marker: Path,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 15,
    post: Optional[Callable[..., Any]] = None,
) -> int:
    """
    Send queued retries plus ``records``; requeue only what is retryable.

    Returns the number of records accepted. Does nothing while paused.
    """
    if is_paused(pause_marker):
        logger.info("Collection paused after an authorization error; nothing sent")
        return 0

    pending = queue.load()
    sent = 0
    still_pending: List[Dict[str, Any]] = []
    if pending:
        ok, retry, pause = send_records(url, [e["record"] for e in pending], headers, timeout, post=post)
        sent += ok
        if pause:
            pause_collection(pause_marker, pause)
            queue.clear()
            return sent
        by_id = {id(e["record"]): e for e in pending}
        for record in retry:
            still_pending.extend(PendingQueue.entries_for([record], by_id.get(id(record))))

    if records:
        ok, retry, pause = send_records(url, records, headers, timeout, post=post)
        sent += ok
        if pause:
            pause_collection(pause_marker, pause)
            queue.clear()
            return sent
        still_pending.extend(PendingQueue.entries_for(retry))

    if still_pending:
        queue.save(still_pending)
    else:
        queue.clear()
    return sent
