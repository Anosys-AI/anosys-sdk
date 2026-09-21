"""
CLI entry point for anosys-codex.

Commands:
  install    Register the AnoSys notify hook in ~/.codex/config.toml
  uninstall  Remove the AnoSys notify hook from ~/.codex/config.toml
  status     Show current hook registration status
  run        Execute the hook (invoked by Codex CLI on notify events)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from anosys_sdk_codex.installer import (
    HOOK_COMMAND,
    INGESTION_URL,
    backup,
    get_config_path,
    get_env_path,
    has_anosys_hook,
    load_toml,
    remove_codex_config,
    remove_codex_env,
    update_codex_config,
    update_codex_env,
    validate_api_key,
)


def _prompt(prompt: str, default: str = "") -> str:
    try:
        val = input(prompt).strip()
        return val if val else default
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)


def cmd_install(args: argparse.Namespace) -> None:
    print("\nAnoSys OpenAI Codex Hook Installer")
    print("=" * 45)

    redaction = args.redaction
    if not redaction and not args.no_redaction:
        choice = _prompt("Enable content redaction? (y/N): ", "n").lower()
        redaction = choice == "y"

    api_key = args.api_key
    if not api_key:
        api_key = _prompt("AnoSys API key for logs (leave blank to skip): ")

    if api_key:
        print("Validating Logs API key...")
        if not validate_api_key(api_key, "codex"):
            print("⚠️  Warning: Logs API key validation failed (invalid key or incompatible type).")
        else:
            print("✅ Logs API key is valid.")

    auto_update = args.auto_update
    if auto_update is None:
        choice = _prompt("Would you like to automatically update ~/.codex/config.toml? (Y/n): ", "y").lower()
        auto_update = choice != "n"

    config_path = get_config_path()
    env_path = get_env_path()

    if auto_update:
        print(f"\nUpdating {config_path} ...")
        backup_path = backup(config_path)
        update_codex_config(HOOK_COMMAND, path=config_path)
        update_codex_env(api_key=api_key, redaction=redaction, path=env_path)

        if backup_path:
            print(f"  Backed up original settings -> {backup_path}")
        print(f"  Hook command registered in notify: {HOOK_COMMAND}")
        print(f"  Ingestion URL: {INGESTION_URL}")
        if api_key:
            masked = ("*" * (len(api_key) - 4)) + api_key[-4:] if len(api_key) > 4 else "****"
            print(f"  Logs API key: {masked}")
        print(f"  Redaction: {'enabled' if redaction else 'disabled'}")
        print("\n✅ Codex hook installed successfully.")
        print("\n⚠️  IMPORTANT (Codex Security Trust):")
        print("   In your next Codex CLI session, run the '/hooks' command")
        print(f"   and approve the '{HOOK_COMMAND}' entry to allow tracing.\n")
    else:
        print("\n================================================================")
        print("Add the following to your ~/.codex/config.toml file:")
        print(f'\nnotify = ["{HOOK_COMMAND}"]\n')
        print("And create ~/.codex/anosys-env.sh with:")
        print(f'export ANOSYS_HOOK_APIKEY="{api_key}"')
        print(f'export ANOSYS_HOOK_ENDPOINT_URL="{INGESTION_URL}"')
        print(f'export REDACTION="{"true" if redaction else "false"}"')
        print("================================================================\n")


def cmd_uninstall(args: argparse.Namespace) -> None:
    print("\nAnoSys OpenAI Codex Hook Uninstaller")
    print("=" * 45)

    config_path = get_config_path()
    env_path = get_env_path()

    backup_path = backup(config_path)
    removed_config = remove_codex_config(config_path)
    removed_env = remove_codex_env(env_path)

    if backup_path:
        print(f"  Backed up settings -> {backup_path}")
    if removed_config:
        print(f"  Removed hook entry from {config_path}")
    else:
        print(f"  No AnoSys hook entry found in {config_path}")

    if removed_env:
        print(f"  Removed {env_path}")

    print("\n✅ AnoSys Codex hook uninstalled successfully.\n")


def cmd_status(args: argparse.Namespace) -> None:
    config_path = get_config_path()
    env_path = get_env_path()

    print(f"\nAnoSys Codex Hook Status")
    print("=" * 45)
    print(f"Codex Config: {config_path}")
    print(f"Env File:     {env_path}")

    if not config_path.is_file():
        print("\n⚠️  Codex config.toml does not exist.")
        return

    data = load_toml(config_path)
    installed = has_anosys_hook(data)

    if installed:
        print("\nStatus: ✅ Installed and active in config.toml")
        notify_list = data.get("notify", [])
        print(f"Notify hooks: {notify_list}")
    else:
        print("\nStatus: ❌ Not registered in config.toml")

    if env_path.is_file():
        print(f"Env file exists: ✅ Yes")
    else:
        print(f"Env file exists: ❌ No")
    print()


def cmd_run(args: argparse.Namespace) -> None:
    from anosys_sdk_codex.hook_runner import run
    run()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="anosys-codex",
        description="AnoSys CLI integration for OpenAI Codex",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    p_install = subparsers.add_parser("install", help="Install AnoSys hook into ~/.codex/config.toml")
    p_install.add_argument("--api-key", help="AnoSys logs API key")
    p_install.add_argument("--redaction", action="store_true", default=False, help="Enable content redaction")
    p_install.add_argument("--no-redaction", action="store_true", default=False, help="Disable content redaction")
    p_install.add_argument("--auto-update", dest="auto_update", action="store_true", default=None)
    p_install.add_argument("--no-auto-update", dest="auto_update", action="store_false")
    p_install.set_defaults(func=cmd_install)

    p_uninstall = subparsers.add_parser("uninstall", help="Remove AnoSys hook from ~/.codex/config.toml")
    p_uninstall.set_defaults(func=cmd_uninstall)

    p_status = subparsers.add_parser("status", help="Check hook installation status")
    p_status.set_defaults(func=cmd_status)

    p_run = subparsers.add_parser("run", help="Run the hook (invoked by Codex notify)")
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
