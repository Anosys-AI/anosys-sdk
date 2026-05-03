"""
CLI entry point for anosys-claude-code.

Commands:
  install    Register the AnoSys Stop hook in ~/.claude/settings.json
  uninstall  Remove the AnoSys Stop hook from ~/.claude/settings.json
  status     Show current hook registration status
  run        Execute the hook (invoked by Claude Code on every Stop event)
"""

import argparse
import asyncio
import json
import shutil
import sys

from anosys_sdk_claude_code.installer import (
    ANOSYS_ENV_KEYS,
    BACKUP_PATH,
    SETTINGS_PATH,
    backup,
    get_anosys_hook_command,
    has_anosys_hook,
    load_settings,
    remove_env,
    remove_stop_hooks,
    update_env,
    update_stop_hooks,
    write_atomic,
)

HOOK_COMMAND = "anosys-claude-code run"
DEFAULT_ENDPOINT = "https://api.anosys.ai"


def _prompt(prompt: str, default: str = "") -> str:
    try:
        val = input(prompt).strip()
        return val if val else default
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)


def cmd_install(args: argparse.Namespace) -> None:
    print("\nAnoSys Claude Code Hook Installer")
    print("=" * 40)

    api_key = args.api_key
    if not api_key:
        api_key = _prompt(
            "AnoSys API key (leave blank to skip, can set ANOSYS_HOOK_API_KEY later): "
        )

    endpoint = args.endpoint or _prompt(
        f"AnoSys endpoint URL [{DEFAULT_ENDPOINT}]: ", DEFAULT_ENDPOINT
    )

    redaction = args.redaction
    if not redaction and not args.no_redaction:
        choice = _prompt("Enable content redaction? (y/N): ", "n").lower()
        redaction = choice == 'y'

    new_env: dict = {
        "ANOSYS_HOOK_ENDPOINT_URL": endpoint,
    }
    if api_key:
        new_env["ANOSYS_HOOK_API_KEY"] = api_key
    if redaction:
        new_env["REDACTION"] = "true"

    print(f"\nUpdating {SETTINGS_PATH} ...")
    settings = load_settings()
    backup()
    settings = update_env(settings, new_env)
    settings = update_stop_hooks(settings, HOOK_COMMAND)
    write_atomic(SETTINGS_PATH, settings)

    print(f"  Backed up original settings -> {BACKUP_PATH}")
    print(f"  Hook command registered: {HOOK_COMMAND}")
    print(f"  Endpoint: {endpoint}")
    if api_key:
        print(f"  API key: {'*' * (len(api_key) - 4)}{api_key[-4:]}")
    print(f"  Redaction: {'enabled' if redaction else 'disabled'}")
    print("\nDone. The hook will fire automatically after each Claude Code session.")


def cmd_uninstall(args: argparse.Namespace) -> None:
    print(f"\nRemoving AnoSys hook from {SETTINGS_PATH} ...")
    settings = load_settings()
    if not has_anosys_hook(settings):
        print("  No AnoSys hook found — nothing to remove.")
        return
    backup()
    settings = remove_stop_hooks(settings)
    settings = remove_env(settings)
    write_atomic(SETTINGS_PATH, settings)
    print(f"  Backed up original settings -> {BACKUP_PATH}")
    print("  AnoSys hook removed successfully.")


def cmd_status(args: argparse.Namespace) -> None:
    settings = load_settings()
    if has_anosys_hook(settings):
        cmd = get_anosys_hook_command(settings)
        print(f"AnoSys hook is INSTALLED")
        print(f"  Command: {cmd}")
        env = settings.get("env", {})
        endpoint = env.get("ANOSYS_HOOK_ENDPOINT_URL", "(not set)")
        has_key = "ANOSYS_HOOK_API_KEY" in env
        redaction = env.get("REDACTION", "false")
        print(f"  Endpoint: {endpoint}")
        print(f"  API key: {'set' if has_key else 'not set'}")
        print(f"  Redaction: {redaction}")
    else:
        print("AnoSys hook is NOT installed.")
        print(f"  Run 'anosys-claude-code install' to set it up.")


def cmd_run(args: argparse.Namespace) -> None:
    from anosys_sdk_claude_code.hook_runner import main
    asyncio.run(main())


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="anosys-claude-code",
        description="AnoSys observability hook for Claude Code"
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    p_install = sub.add_parser("install", help="Register the AnoSys Stop hook")
    p_install.add_argument("--api-key", metavar="KEY", help="AnoSys API key")
    p_install.add_argument("--endpoint", metavar="URL", help=f"Endpoint URL (default: {DEFAULT_ENDPOINT})")
    p_install.add_argument("--redaction", action="store_true", help="Enable content redaction")
    p_install.add_argument("--no-redaction", action="store_true", help="Skip redaction prompt")
    p_install.set_defaults(func=cmd_install)

    p_uninstall = sub.add_parser("uninstall", help="Remove the AnoSys Stop hook")
    p_uninstall.set_defaults(func=cmd_uninstall)

    p_status = sub.add_parser("status", help="Show hook registration status")
    p_status.set_defaults(func=cmd_status)

    p_run = sub.add_parser("run", help="Execute the hook (called by Claude Code)")
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
