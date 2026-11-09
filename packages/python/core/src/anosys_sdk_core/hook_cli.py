"""
Shared CLI pieces for the coding-agent hooks (Claude Code, Codex, Antigravity).

Each hook's CLI wires these into ``privacy``, ``doctor`` and ``purge``
commands so the three tools behave the same way.
"""

import argparse
import logging
import logging.handlers
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

from anosys_sdk_core.privacy import (
    FULL, LEVELS, POLICY_URL, POLICY_VERSION,
    consent_path, effective_level, read_consent, write_consent,
)

POLICY_SUMMARY = f"""\
AnoSys data-collection policy {POLICY_VERSION} ({POLICY_URL})

At `full`, the hook sends the content of your sessions to AnoSys: prompts,
assistant answers, thinking, tool inputs and outputs, shell commands, file
paths and file contents that pass through the tool. Secret-shaped strings
(API keys, tokens, private keys) are scrubbed on a best-effort basis.
At `metadata` (the default) only ids, timestamps, models, token and cost
numbers, durations, tool names, project/branch names and your OS username
are sent. Set ANOSYS_ENCRYPTION_KEY to encrypt content so only your browser
can read it. Each record carries the level and policy version you chose.
"""


def add_privacy_parser(subparsers, tool: str) -> None:
    p = subparsers.add_parser("privacy", help="Show or change what the hook collects")
    p.add_argument("level", nargs="?", choices=["status", *LEVELS], default="status",
                   help="status (default), off, metadata or full")
    p.add_argument("--accept-policy", metavar="VERSION",
                   help=f"accept the data-collection policy non-interactively (current: {POLICY_VERSION})")
    p.set_defaults(func=lambda args: cmd_privacy(args, tool))


def cmd_privacy(args: argparse.Namespace, tool: str) -> None:
    if args.level == "status":
        level, source = effective_level()
        consent = read_consent()
        print(f"\n{tool}: collecting at '{level}' (from {source})")
        print(f"Consent file: {consent_path()}")
        if consent.get("policy_version"):
            print(f"Policy accepted: {consent['policy_version']} on {consent.get('accepted_at')}")
        print("Change it with: privacy off | privacy metadata | privacy full\n")
        return

    accept = args.accept_policy
    if args.level == FULL and accept is None:
        print(POLICY_SUMMARY)
        try:
            answer = input(f"Type 'accept' to accept policy {POLICY_VERSION}: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if answer != "accept":
            print("Policy not accepted; level unchanged.")
            sys.exit(1)
        accept = POLICY_VERSION
    try:
        write_consent(args.level, method="cli" if args.accept_policy is None else "cli-flag", accept_policy=accept)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    level, source = effective_level()
    print(f"{tool}: now collecting at '{level}' (from {source}).")


def add_maintenance_parsers(subparsers, purge_paths: Callable[[], List[Path]],
                            doctor: Callable[[], None]) -> None:
    p = subparsers.add_parser("purge", help="Delete local queued records and logs")
    p.add_argument("-y", "--yes", action="store_true", help="Do not ask for confirmation")
    p.set_defaults(func=lambda args: cmd_purge(args, purge_paths()))
    d = subparsers.add_parser("doctor", help="Show installed copies, the active hook and local files")
    d.set_defaults(func=lambda args: doctor())


def cmd_purge(args: argparse.Namespace, paths: List[Path]) -> None:
    existing = [p for p in paths if p.exists()]
    if not existing:
        print("Nothing to purge.")
        return
    for p in existing:
        print(f"  {p} ({_size(p)})")
    if not args.yes:
        try:
            if input("Delete these files? (y/N): ").strip().lower() != "y":
                print("Nothing deleted.")
                return
        except (EOFError, KeyboardInterrupt):
            return
    for p in existing:
        try:
            p.unlink()
            print(f"  deleted {p}")
        except OSError as e:
            print(f"  could not delete {p}: {e}")


def _size(path: Path) -> str:
    try:
        n = path.stat().st_size
    except OSError:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def print_doctor(tool: str, executables: List[str], module: str,
                 active_hook: Optional[str], files: Dict[str, Path]) -> None:
    level, source = effective_level()
    print(f"\n{tool} doctor")
    print("=" * 45)
    print(f"Collecting at: {level} (from {source})")
    print(f"This copy:     {sys.executable} -m {module}")
    print(f"Active hook:   {active_hook or 'not installed'}")
    print("\nInstalled copies on PATH:")
    found = False
    for name in executables:
        for directory in os.environ.get("PATH", "").split(os.pathsep):
            candidate = Path(directory) / name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                found = True
                print(f"  {candidate}{'  (cannot run)' if not _runs(candidate) else ''}")
    if not found:
        print("  none")
    print("\nLocal files:")
    for label, path in files.items():
        state = _size(path) if path.exists() else "absent"
        print(f"  {label:<16} {path}  [{state}]")
    print()


def _runs(path: Path) -> bool:
    try:
        subprocess.run([str(path), "--help"], capture_output=True, timeout=10)
        return True
    except Exception:
        return False


def setup_hook_logging(log_file: Path, name: str) -> logging.Logger:
    """
    Hook log: INFO level, rotated at 5 MB (2 backups), file mode 0600.
    Hooks must log ids, sizes and status codes only, never payloads or input.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        if not log_file.exists():
            fd = os.open(log_file, os.O_CREAT | os.O_WRONLY, stat.S_IRUSR | stat.S_IWUSR)
            os.close(fd)
        try:
            os.chmod(log_file, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        handler: logging.Handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=5_000_000, backupCount=2, encoding="utf-8")
    except OSError:
        # read-only home, full disk, ...: the hook still runs, without a log
        handler = logging.NullHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False  # never echo hook logs to the host tool's console
    # core helpers log through their own loggers; send them to the same file
    for core in ("anosys_sdk_core.transport", "anosys_sdk_core.encryption"):
        logging.getLogger(core).addHandler(handler)
        logging.getLogger(core).setLevel(logging.INFO)
    return logger


def run_hook_safely(fn, logger: Optional[logging.Logger] = None) -> None:
    """
    Run a hook body so that it can never break the host tool: any exception is
    logged by type only and swallowed (the hook exits 0 and prints nothing).
    """
    try:
        fn()
    except Exception as e:  # noqa: BLE001 - the host tool must never see a hook failure
        try:
            (logger or logging.getLogger("anosys_hook")).error("Hook failed (%s)", type(e).__name__)
        except Exception:
            pass


def which(name: str) -> Optional[str]:
    return shutil.which(name)
