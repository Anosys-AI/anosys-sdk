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
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

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
    from anosys_sdk_core.encryption import JSON_COLUMNS

    for key in order:
        if json_size([result]) <= target:
            break
        value = record[key]
        mark = TRUNCATION_MARK.format(size=len(value.encode("utf-8")))
        # JSON columns must stay valid JSON: the cut text is stored as a JSON string
        wrap = (lambda text: json.dumps(text)) if key in JSON_COLUMNS else (lambda text: text)
        if _is_encrypted(value):
            # a cut ciphertext cannot be decrypted: replace the whole value
            result[key] = wrap(mark.lstrip("."))
            continue
        text = value
        # escaped characters take more bytes than characters, so cut until it fits
        for _ in range(6):
            excess = json_size([result]) - target
            if excess <= 0 or not text:
                break
            text = text[:max(0, len(text) - excess - len(mark) - 64)]
            result[key] = wrap(text + mark)
    if json_size([result]) <= target:
        logger.warning("Record over the %d-byte limit was truncated", target)
        return result
    logger.warning("Dropped a record that does not fit in %d bytes even after truncation", target)
    return None


def _chunk_pairs(records: List[Dict[str, Any]], limit: Optional[int] = None):
    """Request bodies as (original, fitted) pairs, so failures can be traced to the original."""
    target = _target(limit)
    chunks = []
    current = []
    current_size = 2  # "[]"
    for record in records:
        fitted = fit_record(record, limit)
        if fitted is None:
            continue
        size = json_size(fitted) + 1  # comma
        if current and current_size + size > target:
            chunks.append(current)
            current, current_size = [], 2
        current.append((record, fitted))
        current_size += size
    if current:
        chunks.append(current)
    return chunks


def chunk_records(records: List[Dict[str, Any]], limit: Optional[int] = None) -> List[List[Dict[str, Any]]]:
    """Split records into request bodies under the byte limit (oversized ones fitted or dropped)."""
    return [[fitted for _, fitted in chunk] for chunk in _chunk_pairs(records, limit)]


def post_record(url: str, record: Dict[str, Any], timeout: float = 5,
                headers: Optional[Dict[str, str]] = None, post: Optional[Callable] = None):
    """
    POST one already-encrypted record, fitted under the size limit. Returns
    the response, or None when the record had to be dropped. Used by the
    application SDKs, which send one span or call per request.
    """
    if not url:
        return None  # no ingestion endpoint (missing or unresolvable API key)
    fitted = fit_record(record)
    if fitted is None:
        return None
    if post is None:
        import requests
        post = requests.post
    return post(url, json=fitted, timeout=timeout, headers=headers)


# ── background sending for the application SDKs ────────────────────────────────

class BackgroundSender:
    """
    Sends application records off the caller's thread.

    Instrumented code (an LLM call, a decorated function, a span end) must not
    wait on AnoSys. Records go to a bounded in-memory queue drained by one
    daemon thread; when the queue is full the record is dropped (warned once),
    so memory stays bounded when ingestion is slow or down. Nothing is written
    to disk and nothing is retried: application telemetry is best effort.
    At exit the queue is drained for at most ``flush_seconds``.
    """

    def __init__(self, max_queue: int = 1000, timeout: float = 5, flush_seconds: float = 2):
        import queue
        import threading

        self._queue: "queue.Queue" = queue.Queue(maxsize=max_queue)
        self._timeout = timeout
        self._flush_seconds = flush_seconds
        self._lock = threading.Lock()
        self._thread: Optional["threading.Thread"] = None
        self._warned_full = False
        self.post: Optional[Callable] = None  # injectable for tests

    def _ensure_thread(self) -> None:
        import atexit
        import threading

        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name="anosys-sender", daemon=True)
                self._thread.start()
                atexit.register(self.flush)

    def submit(self, url: str, record: Dict[str, Any]) -> bool:
        """Queue one record; False when it was dropped (no endpoint or queue full)."""
        import queue

        if not url or record is None:
            return False
        try:
            self._queue.put_nowait((url, record))
        except queue.Full:
            if not self._warned_full:
                self._warned_full = True
                logger.warning("AnoSys send queue is full; telemetry is being dropped")
            return False
        self._ensure_thread()
        return True

    def _run(self) -> None:
        while True:
            url, record = self._queue.get()
            try:
                response = post_record(url, record, timeout=self._timeout, post=self.post)
                status = getattr(response, "status_code", 200) if response is not None else None
                if status is not None and status >= 400:
                    logger.error("AnoSys rejected a record (HTTP %s)", status)
            except Exception as e:  # never surfaces to the instrumented application
                logger.error("AnoSys send failed (%s)", type(e).__name__)
            finally:
                self._queue.task_done()

    def flush(self, seconds: Optional[float] = None) -> bool:
        """Wait (bounded) for queued records to be sent. True when the queue emptied."""
        deadline = time.monotonic() + (self._flush_seconds if seconds is None else seconds)
        while self._queue.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(0.01)
        return not self._queue.unfinished_tasks


_SENDER = BackgroundSender()


def send_app_record(url: str, record: Optional[Dict[str, Any]]) -> bool:
    """
    The one way application SDKs send a prepared (filtered, encrypted) record:
    in the background, size-limited, never blocking or raising in the caller.
    """
    return _SENDER.submit(url, record)


def flush_app_records(seconds: float = 2) -> bool:
    """Wait up to ``seconds`` for background records (tests, short-lived scripts)."""
    return _SENDER.flush(seconds)


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
    deadline: Optional[float] = None,
) -> Tuple[int, List[Dict[str, Any]], Optional[int]]:
    """
    POST records in size-limited batches.

    ``deadline`` (a ``time.monotonic()`` value) bounds the total time: chunks not
    sent by then are returned as retryable. After a timeout or connection error
    the remaining chunks are not attempted (they would wait out the same timeout).

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
    unreachable = False
    for pairs in _chunk_pairs(records, limit):
        chunk = [fitted for _, fitted in pairs]
        originals = [original for original, _ in pairs]  # retries keep their queue history
        if pause is not None:
            break  # the key is rejected; don't send (or queue) the rest
        remaining = None if deadline is None else deadline - time.monotonic()
        if unreachable or (remaining is not None and remaining < 0.5):
            retryable.extend(originals)  # out of time, or ingestion is down: keep for later
            continue
        try:
            request_timeout = timeout if remaining is None else min(timeout, remaining)
            response = post(url, json=chunk, headers=headers or {}, timeout=request_timeout)
            status = getattr(response, "status_code", 200)
        except Exception as e:  # timeout, connection error
            logger.warning("Ingestion unreachable (%s); %d record(s) kept for retry", type(e).__name__, len(chunk))
            retryable.extend(originals)
            unreachable = True
            continue
        if status < 300:
            sent += len(chunk)
        elif is_permanent(status):
            logger.warning("Ingestion rejected %d record(s) with %d; dropped", len(chunk), status)
            if status in PAUSE_STATUS:
                pause = status
        else:
            logger.warning("Ingestion returned %d; %d record(s) kept for retry", status, len(chunk))
            retryable.extend(originals)
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
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")  # unique per process
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
    budget: Optional[float] = None,
    metadata_fields: Optional[Iterable[str]] = None,
    cwd: Optional[str] = None,
) -> int:
    """
    Send queued retries plus ``records``; requeue only what is retryable.

    The whole call takes at most ``budget`` seconds (ANOSYS_HOOK_TIME_BUDGET,
    default 20), so a hook never holds up the coding tool for long; what is not
    sent in time stays queued. Runs of several hooks at once are serialised on a
    lock file; a run that cannot get the lock sends only its new records and
    leaves the queue to the other run.

    With ``metadata_fields`` (the hook's allowlist), queued records are brought
    in line with the current level before they are sent: after a downgrade to
    ``metadata`` the content of records queued at ``full`` is removed, and at
    ``off`` the queue is emptied without sending.

    Returns the number of records accepted. Does nothing while paused.
    """
    if is_paused(pause_marker):
        logger.info("Collection paused after an authorization error; nothing sent")
        return 0

    deadline = time.monotonic() + (hook_time_budget() if budget is None else budget)
    with _QueueLock(queue.path) as locked:
        if not locked:
            ok, retry, pause = send_records(url, records, headers, timeout, post=post, deadline=deadline)
            if pause:
                pause_collection(pause_marker, pause)
            if retry:
                logger.warning("Queue busy (another hook run); %d record(s) not kept for retry", len(retry))
            return ok
        return _deliver_locked(url, records, queue, pause_marker, headers, timeout, post, deadline, metadata_fields, cwd=cwd)


def hook_time_budget() -> float:
    """Seconds a hook may spend sending (ANOSYS_HOOK_TIME_BUDGET, default 20)."""
    try:
        value = float(os.environ.get("ANOSYS_HOOK_TIME_BUDGET", 20))
        return value if value > 0 else 20.0
    except ValueError:
        return 20.0


class _QueueLock:
    """Exclusive lock file next to the queue; stale locks (> 120 s) are broken."""

    STALE_SECONDS = 120

    def __init__(self, queue_path: Path, wait: float = 2.0):
        self.path = Path(str(queue_path) + ".lock")
        self.wait = wait
        self.held = False

    def __enter__(self) -> bool:
        deadline = time.monotonic() + self.wait
        while True:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, stat.S_IRUSR | stat.S_IWUSR)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                self.held = True
                return True
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > self.STALE_SECONDS:
                        self.path.unlink()
                        continue
                except OSError:
                    pass
                if time.monotonic() >= deadline:
                    return False
                time.sleep(0.05)
            except OSError:
                return False  # read-only or full disk: run without the queue

    def __exit__(self, *exc) -> None:
        if self.held:
            try:
                self.path.unlink()
            except OSError:
                pass


def _apply_current_level(pending: List[Dict[str, Any]], metadata_fields: Iterable[str], cwd: Optional[str] = None) -> List[Dict[str, Any]]:
    """Downgrade queued entries to the level in force now (consent can be withdrawn while they wait)."""
    from anosys_sdk_core.privacy import FULL, METADATA, OFF, effective_level, filter_fields

    level, _ = effective_level(cwd=cwd)
    if level == OFF:
        return []
    if level == FULL:
        return pending
    keep = set(metadata_fields)
    for entry in pending:
        record = entry.get("record") or {}
        if str(record.get("cvs198", "")).startswith(f"{FULL};"):
            entry["record"] = filter_fields(record, METADATA, keep)
    return pending


def _deliver_locked(url, records, queue, pause_marker, headers, timeout, post, deadline, metadata_fields=None, cwd=None) -> int:
    pending = queue.load()
    if metadata_fields is not None and pending:
        pending = _apply_current_level(pending, metadata_fields, cwd=cwd)
    sent = 0
    still_pending: List[Dict[str, Any]] = []
    if pending:
        ok, retry, pause = send_records(url, [e["record"] for e in pending], headers, timeout, post=post,
                                        deadline=deadline)
        sent += ok
        if pause:
            pause_collection(pause_marker, pause)
            queue.clear()
            return sent
        by_id = {id(e["record"]): e for e in pending}
        for record in retry:
            still_pending.extend(PendingQueue.entries_for([record], by_id.get(id(record))))

    if records:
        ok, retry, pause = send_records(url, records, headers, timeout, post=post, deadline=deadline)
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
