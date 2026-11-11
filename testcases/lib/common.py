"""Shared helpers for the Python checks: result reporting and isolated homes."""

import json
import os
import sys
import tempfile
from pathlib import Path

_failures = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(("PASS " if ok else "FAIL ") + name + ("" if ok or not detail else f"  -> {detail}"))
    if not ok:
        _failures.append(name)
    return ok


def finish() -> None:
    sys.exit(1 if _failures else 0)


def isolated_home(prefix: str = "anosys-tc-") -> Path:
    """A throwaway HOME with its own consent file, so no check touches the real machine state."""
    home = Path(tempfile.mkdtemp(prefix=prefix))
    os.environ["HOME"] = str(home)
    os.environ["ANOSYS_CONSENT_FILE"] = str(home / ".anosys" / "consent.json")
    for var in ("ANOSYS_DISABLE", "ANOSYS_COLLECTION_LEVEL", "REDACTION", "ANOSYS_ENCRYPTION_KEY",
                "ANOSYS_ENCRYPTION_SALT", "ANOSYS_ENCRYPTED_COLUMNS", "ANOSYS_CLAUDE_PIXEL",
                "ANOSYS_PIXEL_TYPE", "ANOSYS_API_KEY", "ANOSYS_API_URL", "CODEX_HOME"):
        os.environ.pop(var, None)
    return home


def ingested(out_dir: str, tag: str) -> list:
    """Every record the fake ingestion server received under ``tag``."""
    path = Path(out_dir) / f"{tag}.jsonl"
    records = []
    if path.exists():
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            records.extend(data if isinstance(data, list) else [data])
    return records


def is_encrypted(value) -> bool:
    return isinstance(value, str) and (value.startswith("enc2:") or value.startswith('"enc2:'))
