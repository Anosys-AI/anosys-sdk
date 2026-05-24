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
import sys

from anosys_sdk_claude_code.installer import (
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

    redaction = args.redaction
    if not redaction and not args.no_redaction:
        choice = _prompt("Enable content redaction? (y/N): ", "n").lower()
        redaction = choice == 'y'

    api_key = args.api_key
    if not api_key:
        api_key = _prompt("AnoSys API key for logs (leave blank to skip): ")

    # OTEL setup
    otel_api_key = args.otel_key
    if otel_api_key is None:
        otel_api_key = _prompt("Enter your AnoSys API Key (OTEL type, leave blank to skip OTEL): ")
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
    if redaction:
        new_env["REDACTION"] = "true"
    if enable_otel:
        new_env["CLAUDE_CODE_ENABLE_TELEMETRY"] = "1"
        new_env["OTEL_SERVICE_NAME"] = "claude-code"
        new_env["OTEL_TRACES_EXPORTER"] = "otlp"
        new_env["OTEL_METRICS_EXPORTER"] = "otlp"
        new_env["OTEL_LOGS_EXPORTER"] = "otlp"
        new_env["OTEL_EXPORTER_OTLP_PROTOCOL"] = "http/protobuf"
        new_env["OTEL_EXPORTER_OTLP_ENDPOINT"] = INGESTION_URL
        new_env["OTEL_EXPORTER_OTLP_HEADERS"] = f"anosys-apikey={otel_api_key}"

    if auto_update:
        print(f"\nUpdating {SETTINGS_PATH} ...")
        settings = load_settings()
        backup_path = backup()
        settings = update_env(settings, new_env)
        settings = update_stop_hooks(settings, HOOK_COMMAND)
        write_atomic(SETTINGS_PATH, settings)

        if backup_path:
            print(f"  Backed up original settings -> {backup_path}")
        print(f"  Hook command registered: {HOOK_COMMAND}")
        print(f"  Ingestion URL: {INGESTION_URL}")
        if api_key:
            print(f"  Logs API key: {'*' * (len(api_key) - 4)}{api_key[-4:]}")
        print(f"  Redaction: {'enabled' if redaction else 'disabled'}")
        if enable_otel:
            print(f"  OTEL: enabled (API key set, ingestion URL: {INGESTION_URL})")
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
                                "command": HOOK_COMMAND,
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
        redaction = env.get("REDACTION", "false")
        print(f"  Ingestion URL: {INGESTION_URL}")
        print(f"  Logs API key: {'set' if has_logs_key else 'not set'}")
        print(f"  OTEL API key: {'set' if has_otel_key else 'not set'}")
        print(f"  Redaction: {redaction}")
    else:
        print("AnoSys hook is NOT installed.")
        print("  Run 'anosys-claude-code install' to set it up.")


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
    p_install.add_argument("--api-key", metavar="KEY", help="AnoSys API key for logs")
    p_install.add_argument("--redaction", action="store_true", help="Enable content redaction")
    p_install.add_argument("--no-redaction", action="store_true", help="Skip redaction prompt")
    p_install.add_argument("--otel-key", metavar="KEY", help="AnoSys OTEL API key")
    p_install.add_argument("--auto-update", action="store_true", default=None, help="Automatically update settings.json")
    p_install.add_argument("--no-auto-update", action="store_false", dest="auto_update", help="Do not automatically update settings.json")
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
