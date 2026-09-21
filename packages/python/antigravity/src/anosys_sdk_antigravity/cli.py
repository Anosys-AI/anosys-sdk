"""
CLI entry point for anosys-antigravity.

Commands:
  install    Register the AnoSys tracing hook in ~/.gemini/config/hooks.json
  uninstall  Remove the AnoSys tracing hook from hooks.json
  status     Show current hook registration and configuration status
  run        Execute hook handler (invoked by Antigravity on PreInvocation/Stop)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from anosys_sdk_antigravity.constants import (
    DEFAULT_INGESTION_URL,
    HOOK_COMMAND,
    HOOK_NAME,
)
from anosys_sdk_antigravity.installer import (
    backup,
    get_env_path,
    get_hooks_path,
    has_anosys_hook,
    load_json,
    remove_env_config,
    remove_hooks_config,
    update_env_config,
    update_hooks_config,
    validate_api_key,
)


def _prompt(prompt_text: str, default: str = "") -> str:
    try:
        val = input(prompt_text).strip()
        return val if val else default
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)


def cmd_install(args: argparse.Namespace) -> None:
    print("\nAnoSys Google Antigravity Hook Installer")
    print("=" * 45)

    yes = getattr(args, "yes", False)
    workspace = getattr(args, "workspace", False)
    hooks_path = get_hooks_path(workspace=workspace)
    env_path = get_env_path(workspace=workspace)

    redaction = getattr(args, "redaction", False)
    if not redaction and not getattr(args, "no_redaction", False):
        if yes:
            redaction = False
        else:
            choice = _prompt("Enable content redaction? (y/N): ", "n").lower()
            redaction = choice == "y"

    api_key = (
        getattr(args, "api_key", None)
        or os.environ.get("ANOSYS_HOOK_APIKEY")
        or os.environ.get("ANOSYS_API_KEY")
        or ""
    )
    if not api_key and not yes:
        api_key = _prompt("AnoSys API key for logs (leave blank to skip): ")

    if api_key:
        print("Validating Logs API key...")
        if not validate_api_key(api_key, "cc"):
            print("⚠️  Warning: Logs API key validation failed: key does not belong to a CC (Claude Code / Codex / Antigravity) pixel or is invalid.")
        else:
            print("✅ Logs API key is valid (CC pixel).")

    endpoint_url = getattr(args, "endpoint_url", None) or os.environ.get("ANOSYS_HOOK_ENDPOINT_URL") or DEFAULT_INGESTION_URL

    auto_update = getattr(args, "auto_update", None)
    if auto_update is None:
        if yes:
            auto_update = True
        else:
            choice = _prompt(f"Update {hooks_path}? (Y/n): ", "y").lower()
            auto_update = choice != "n"

    if auto_update:
        print(f"\nUpdating {hooks_path} ...")
        backup_path = backup(hooks_path)
        update_hooks_config(hooks_path, command=HOOK_COMMAND)
        update_env_config(env_path, api_key=api_key, endpoint_url=endpoint_url, redaction=redaction)

        if backup_path:
            print(f"  Backed up original settings -> {backup_path}")
        print(f"  Hook '{HOOK_NAME}' registered for events: PreInvocation, Stop")
        print(f"  Ingestion URL: {endpoint_url}")
        if api_key:
            masked = ("*" * (len(api_key) - 4)) + api_key[-4:] if len(api_key) > 4 else "****"
            print(f"  Logs API key: {masked}")
        print(f"  Redaction: {'enabled' if redaction else 'disabled'}")
        print("\n✅ Antigravity hook installed successfully.\n")
    else:
        print("\n================================================================")
        print(f"Add the following to your {hooks_path} file:")
        sample = {
            HOOK_NAME: {
                "PreInvocation": [{"type": "command", "command": f"{HOOK_COMMAND} pre_invocation", "timeout": 30}],
                "Stop": [{"type": "command", "command": f"{HOOK_COMMAND} stop", "timeout": 30}],
            }
        }
        import json
        print(json.dumps(sample, indent=2))
        print(f"\nAnd create {env_path} with:")
        env_sample = {
            "ANOSYS_HOOK_APIKEY": api_key,
            "ANOSYS_HOOK_ENDPOINT_URL": endpoint_url,
            "REDACTION": "true" if redaction else "false",
        }
        print(json.dumps(env_sample, indent=2))
        print("================================================================\n")


def cmd_uninstall(args: argparse.Namespace) -> None:
    print("\nAnoSys Google Antigravity Hook Uninstaller")
    print("=" * 45)

    workspace = getattr(args, "workspace", False)
    hooks_path = get_hooks_path(workspace=workspace)
    env_path = get_env_path(workspace=workspace)

    backup_path = backup(hooks_path)
    removed_hook = remove_hooks_config(hooks_path)
    removed_env = remove_env_config(env_path)

    if backup_path:
        print(f"  Backed up settings -> {backup_path}")
    if removed_hook:
        print(f"  Removed '{HOOK_NAME}' from {hooks_path}")
    else:
        print(f"  No '{HOOK_NAME}' entry found in {hooks_path}")

    if removed_env:
        print(f"  Removed {env_path}")

    print("\n✅ AnoSys Antigravity hook uninstalled successfully.\n")


def cmd_status(args: argparse.Namespace) -> None:
    workspace = getattr(args, "workspace", False)
    hooks_path = get_hooks_path(workspace=workspace)
    env_path = get_env_path(workspace=workspace)

    print(f"\nAnoSys Antigravity Hook Status")
    print("=" * 45)
    print(f"Hooks File: {hooks_path}")
    print(f"Env File:   {env_path}")

    if not hooks_path.is_file():
        print("\nStatus: ❌ hooks.json does not exist.")
    else:
        data = load_json(hooks_path)
        if has_anosys_hook(data):
            print("\nStatus: ✅ Installed and active in hooks.json")
            block = data.get(HOOK_NAME, {})
            print(f"Events configured: {list(block.keys())}")
        else:
            print("\nStatus: ❌ Not registered in hooks.json")

    if env_path.is_file():
        print("Env file exists: ✅ Yes")
        env_data = load_json(env_path)
        key = env_data.get("ANOSYS_HOOK_APIKEY", "")
        if key:
            masked = ("*" * (len(key) - 4)) + key[-4:] if len(key) > 4 else "****"
            print(f"Configured API Key: {masked}")
    else:
        print("Env file exists: ❌ No")
    print()


def cmd_run(args: argparse.Namespace) -> None:
    from anosys_sdk_antigravity.hook_runner import run
    run()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="anosys-antigravity",
        description="AnoSys CLI integration for Google Antigravity",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # install
    p_install = subparsers.add_parser("install", help="Install AnoSys hook into hooks.json")
    p_install.add_argument("--api-key", help="AnoSys logs API key")
    p_install.add_argument("-y", "--yes", action="store_true", default=False, help="Non-interactive mode")
    p_install.add_argument("--redaction", action="store_true", default=False, help="Enable content redaction")
    p_install.add_argument("--no-redaction", action="store_true", default=False, help="Disable content redaction")
    p_install.add_argument("--endpoint-url", default=DEFAULT_INGESTION_URL, help="Ingestion endpoint URL")
    p_install.add_argument("--workspace", action="store_true", default=False, help="Target workspace .agents/hooks.json")
    p_install.add_argument("--auto-update", dest="auto_update", action="store_true", default=None)
    p_install.add_argument("--no-auto-update", dest="auto_update", action="store_false")
    p_install.set_defaults(func=cmd_install)

    # uninstall
    p_uninstall = subparsers.add_parser("uninstall", help="Remove AnoSys hook from hooks.json")
    p_uninstall.add_argument("--workspace", action="store_true", default=False, help="Target workspace .agents/hooks.json")
    p_uninstall.set_defaults(func=cmd_uninstall)

    # status
    p_status = subparsers.add_parser("status", help="Check hook installation status")
    p_status.add_argument("--workspace", action="store_true", default=False, help="Check workspace .agents/hooks.json")
    p_status.set_defaults(func=cmd_status)

    # run
    p_run = subparsers.add_parser("run", help="Run the hook handler")
    p_run.add_argument("event", nargs="?", default="stop", help="Hook event (pre_invocation or stop)")
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
