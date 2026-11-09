"""
CLI entry point for anosys-claude-code.

Commands:
  install    Register the AnoSys Stop hook in ~/.claude/settings.json
  uninstall  Remove the AnoSys Stop hook from ~/.claude/settings.json
  status     Show current hook registration status
  privacy    Show or change what is collected (off | metadata | full)
  doctor     Show installed copies, the active hook and local files
  purge      Delete local queued records and logs
  run        Execute the hook (invoked by Claude Code on every Stop event)
"""

import argparse
import asyncio
import sys

from anosys_sdk_core.hook_cli import add_maintenance_parsers, add_privacy_parser, print_doctor
from anosys_sdk_core.privacy import effective_level

from anosys_sdk_claude_code.installer import (
    SETTINGS_PATH,
    hook_command,
    backup,
    get_anosys_hook_command,
    has_anosys_hook,
    load_settings,
    remove_env,
    remove_stop_hooks,
    update_env,
    update_stop_hooks,
    write_atomic,
    validate_api_key,
)

INGESTION_URL = "https://api.anosys.ai/ingestion"


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
        api_key = _prompt("AnoSys API key for logs (leave blank to skip): ")
    if api_key:
        print("Validating Logs API key...")
        if not validate_api_key(api_key, "claudecode"):
            print("⚠️  Warning: Logs API key validation failed (invalid key or incompatible type).")
        else:
            print("✅ Logs API key is valid.")

    # Claude Code's own OTel export is a separate opt-in (--otel-key): it tags
    # every event with your account email and organization ids.
    otel_api_key = args.otel_key
    if otel_api_key:
        print("Validating OTEL API key...")
        if not validate_api_key(otel_api_key, "otel"):
            print("⚠️  Warning: OTEL API key validation failed (invalid key or incompatible type).")
        else:
            print("✅ OTEL API key is valid.")
    enable_otel = bool(otel_api_key)

    auto_update = args.auto_update
    if auto_update is None:
        choice = _prompt("Would you like to automatically update ~/.claude/settings.json? (Y/n): ", "y").lower()
        auto_update = choice != 'n'

    new_env: dict = {
        "ANOSYS_HOOK_DRY_RUN": "false",
    }
    if api_key:
        new_env["ANOSYS_HOOK_APIKEY"] = api_key
    if enable_otel:
        new_env["CLAUDE_CODE_ENABLE_TELEMETRY"] = "1"
        new_env["OTEL_SERVICE_NAME"] = "claude-code"
        new_env["OTEL_TRACES_EXPORTER"] = "otlp"
        new_env["OTEL_METRICS_EXPORTER"] = "otlp"
        new_env["OTEL_LOGS_EXPORTER"] = "otlp"
        new_env["OTEL_EXPORTER_OTLP_PROTOCOL"] = "http/protobuf"
        new_env["OTEL_EXPORTER_OTLP_ENDPOINT"] = INGESTION_URL
        new_env["OTEL_EXPORTER_OTLP_HEADERS"] = f"anosys-apikey={otel_api_key}"
        new_env["OTEL_METRICS_INCLUDE_ACCOUNT_UUID"] = "false"
        # Prompts and tool details stay out of Claude Code's telemetry: we never set
        # OTEL_LOG_USER_PROMPTS or OTEL_LOG_TOOL_DETAILS.

    if auto_update:
        print(f"\nUpdating {SETTINGS_PATH} ...")
        settings = load_settings()
        backup_path = backup()
        settings = update_env(settings, new_env)
        settings = update_stop_hooks(settings, hook_command())
        write_atomic(SETTINGS_PATH, settings)

        if backup_path:
            print(f"  Backed up original settings -> {backup_path}")
        print(f"  Hook command registered: {hook_command()}")
        print(f"  Ingestion URL: {INGESTION_URL}")
        if api_key:
            print(f"  Logs API key: {'*' * (len(api_key) - 4)}{api_key[-4:]}")
        level, source = effective_level()
        print(f"  Collecting: {level} (from {source})")
        if enable_otel:
            print(f"  Claude Code OTel export: enabled ({INGESTION_URL}); events include your account email")
        print("\nBy default only metadata is sent (no prompts, answers, tool output or files).")
        print("To send full content, accept the data-collection policy: anosys-claude-code privacy full")
        print("\nDone. The hook will fire automatically after each Claude Code session.")
    else:
        print("\n================================================================")
        print("Add the following to your ~/.claude/settings.json file options:")
        print("")
        
        manual_config = {
            "env": new_env,
            "hooks": {
                "Stop": [
                    {
                        "owner": "anosys",
                        "hooks": [
                            {
                                "type": "command",
                                "command": hook_command(),
                            }
                        ]
                    }
                ]
            }
        }
        
        import json
        print(json.dumps(manual_config, indent=2))
        print("")
        print("================================================================")


def cmd_uninstall(args: argparse.Namespace) -> None:
    print(f"\nRemoving AnoSys hook from {SETTINGS_PATH} ...")
    settings = load_settings()
    if not has_anosys_hook(settings):
        print("  No AnoSys hook found — nothing to remove.")
        return
    backup_path = backup()
    settings = remove_stop_hooks(settings)
    settings = remove_env(settings)
    write_atomic(SETTINGS_PATH, settings)
    if backup_path:
        print(f"  Backed up original settings -> {backup_path}")
    print("  AnoSys hook removed successfully.")


def cmd_status(args: argparse.Namespace) -> None:
    settings = load_settings()
    if has_anosys_hook(settings):
        cmd = get_anosys_hook_command(settings)
        print("AnoSys hook is INSTALLED")
        print(f"  Command: {cmd}")
        env = settings.get("env", {})
        has_logs_key = "ANOSYS_HOOK_APIKEY" in env
        has_otel_key = "OTEL_EXPORTER_OTLP_HEADERS" in env
        print(f"  Ingestion URL: {INGESTION_URL}")

        if has_logs_key:
            api_key = env.get("ANOSYS_HOOK_APIKEY")
            print("Validating Logs API key...")
            if not validate_api_key(api_key, "claudecode"):
                print("⚠️  Warning: Logs API key validation failed (invalid key or incompatible type).")
            else:
                print("✅ Logs API key is valid.")
        else:
            print("  Logs API key: not set")

        if has_otel_key:
            otel_headers = env.get("OTEL_EXPORTER_OTLP_HEADERS", "")
            import re
            match = re.search(r"anosys-apikey=(.*)", otel_headers)
            otel_api_key = match.group(1) if match else None
            if otel_api_key:
                print("Validating OTEL API key...")
                if not validate_api_key(otel_api_key, "otel"):
                    print("⚠️  Warning: OTEL API key validation failed (invalid key or incompatible type).")
                else:
                    print("✅ OTEL API key is valid.")
            else:
                print("  OTEL API key: set (unable to extract key)")
        else:
            print("  OTEL API key: not set")

        level, source = effective_level()
        print(f"  Collecting: {level} (from {source})")
    else:
        print("AnoSys hook is NOT installed.")
        print("  Run 'anosys-claude-code install' to set it up.")


def cmd_run(args: argparse.Namespace) -> None:
    from anosys_sdk_claude_code.hook_runner import main
    asyncio.run(main())


def _purge_paths():
    from anosys_sdk_claude_code import hook_runner as h
    from anosys_sdk_claude_code.mapper import UNHANDLED_LOG_PATH
    # hook_state.json is kept on purpose: deleting it would re-send this session
    return [h.PENDING_RECORDS_FILE, h.LOG_FILE, h.LOG_FILE.with_name(h.LOG_FILE.name + ".1"),
            h.LOG_FILE.with_name(h.LOG_FILE.name + ".2"), h.PAUSE_FILE, UNHANDLED_LOG_PATH]


def _doctor() -> None:
    from pathlib import Path
    from anosys_sdk_claude_code import hook_runner as h
    from anosys_sdk_claude_code.mapper import UNHANDLED_LOG_PATH
    settings = load_settings()
    print_doctor(
        "anosys-claude-code", ["anosys-claude-code"], "anosys_sdk_claude_code.cli",
        get_anosys_hook_command(settings) if has_anosys_hook(settings) else None,
        {"settings": Path(SETTINGS_PATH), "state": h.STATE_FILE, "pending queue": h.PENDING_RECORDS_FILE,
         "log": h.LOG_FILE, "legacy dump": UNHANDLED_LOG_PATH},
    )


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

    parser = argparse.ArgumentParser(
        prog="anosys-claude-code",
        description="AnoSys observability hook for Claude Code"
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    p_install = sub.add_parser("install", help="Register the AnoSys Stop hook")
    p_install.add_argument("--api-key", metavar="KEY", help="AnoSys API key for logs")
    # Kept so old install commands still work; collection is set with `privacy`
    p_install.add_argument("--redaction", action="store_true", help=argparse.SUPPRESS)
    p_install.add_argument("--no-redaction", action="store_true", help=argparse.SUPPRESS)
    p_install.add_argument("--otel-key", metavar="KEY",
                           help="Also enable Claude Code's own OTel export (includes your account email)")
    p_install.add_argument("--auto-update", action="store_true", default=None, help="Automatically update settings.json")
    p_install.add_argument("--no-auto-update", action="store_false", dest="auto_update", help="Do not automatically update settings.json")
    p_install.set_defaults(func=cmd_install)

    p_uninstall = sub.add_parser("uninstall", help="Remove the AnoSys Stop hook")
    p_uninstall.set_defaults(func=cmd_uninstall)

    p_status = sub.add_parser("status", help="Show hook registration status")
    p_status.set_defaults(func=cmd_status)

    add_privacy_parser(sub, "anosys-claude-code")
    add_maintenance_parsers(sub, _purge_paths, _doctor)

    p_run = sub.add_parser("run", help="Execute the hook (called by Claude Code)")
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
