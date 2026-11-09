"""
CLI entry point for anosys-codex.

Commands:
  install    Register the AnoSys notify hook in ~/.codex/config.toml
  uninstall  Remove the AnoSys notify hook from ~/.codex/config.toml
  status     Show current hook registration status
  privacy    Show or change what is collected (off | metadata | full)
  doctor     Show installed copies, the active hook and local files
  purge      Delete local queued records and logs
  run        Execute the hook (invoked by Codex CLI on notify events)
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from anosys_sdk_core.hook_cli import add_maintenance_parsers, add_privacy_parser, print_doctor
from anosys_sdk_core.privacy import effective_level

from anosys_sdk_codex.installer import (
    INGESTION_URL,
    hook_command,
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

    yes = getattr(args, "yes", False)

    api_key = args.api_key or os.environ.get("ANOSYS_API_KEY") or os.environ.get("ANOSYS_HOOK_APIKEY") or ""
    if not api_key and not yes:
        api_key = _prompt("AnoSys API key for logs (leave blank to skip): ")

    if api_key:
        print("Validating Logs API key...")
        if not validate_api_key(api_key, "cc"):
            print("⚠️  Warning: Logs API key validation failed: key does not belong to a CC (Claude Code / Codex) pixel or is invalid.")
        else:
            print("✅ Logs API key is valid (CC pixel).")

    auto_update = args.auto_update
    if auto_update is None:
        if yes:
            auto_update = True
        else:
            choice = _prompt("Would you like to automatically update ~/.codex/config.toml? (Y/n): ", "y").lower()
            auto_update = choice != "n"

    config_path = get_config_path()
    env_path = get_env_path()

    if auto_update:
        print(f"\nUpdating {config_path} ...")
        backup_path = backup(config_path)
        update_codex_config(path=config_path)
        update_codex_env(api_key=api_key, path=env_path)

        if backup_path:
            print(f"  Backed up original settings -> {backup_path}")
        print(f"  Hook command registered in notify: {hook_command()}")
        print(f"  Ingestion URL: {INGESTION_URL}")
        if api_key:
            masked = ("*" * (len(api_key) - 4)) + api_key[-4:] if len(api_key) > 4 else "****"
            print(f"  Logs API key: {masked}")
        level, source = effective_level()
        print(f"  Collecting: {level} (from {source})")
        print("\n✅ Codex hook installed successfully.")
        print("\nBy default only metadata is sent (no prompts, answers, commands or files).")
        print("To send full content, accept the data-collection policy: anosys-codex privacy full")
        print("\nRestart Codex CLI to load the notification command.")
        print("   The notify callback is separate from lifecycle hooks listed by /hooks.")
        print("   Verify callback execution and delivery in ~/.codex/state/anosys_hook.log.\n")
    else:
        print("\n================================================================")
        print("Add the following to your ~/.codex/config.toml file:")
        print(f"\nnotify = {json.dumps(hook_command())}\n")
        print("And create ~/.codex/anosys-env.sh with:")
        print(f'export ANOSYS_HOOK_APIKEY="{api_key}"')
        print(f'export ANOSYS_HOOK_ENDPOINT_URL="{INGESTION_URL}"')
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

    print("\nAnoSys Codex Hook Status")
    print("=" * 45)
    print(f"Codex Config: {config_path}")
    print(f"Env File:     {env_path}")

    if not config_path.is_file():
        print("\n⚠️  Codex config.toml does not exist.")
        return

    data = load_toml(config_path)
    installed = has_anosys_hook(data)

    level, source = effective_level()
    if installed:
        print("\nStatus: ✅ Installed and active in config.toml")
        print(f"Collecting: {level} (from {source})")
        notify_list = data.get("notify", [])
        print(f"Notify hooks: {notify_list}")
    else:
        print("\nStatus: ❌ Not registered in config.toml")

    if env_path.is_file():
        print("Env file exists: ✅ Yes")
    else:
        print("Env file exists: ❌ No")
    print()


def cmd_run(args: argparse.Namespace) -> None:
    from anosys_sdk_codex.hook_runner import run
    run(sys.argv[2:])


def _purge_paths():
    from anosys_sdk_codex import hook_runner as h
    return [h.PENDING_FILE, h.LOG_FILE, h.LOG_FILE.with_name(h.LOG_FILE.name + ".1"),
            h.LOG_FILE.with_name(h.LOG_FILE.name + ".2"), h.PAUSE_FILE]


def _doctor() -> None:
    from anosys_sdk_codex import hook_runner as h
    data = load_toml(get_config_path())
    print_doctor(
        "anosys-codex", ["anosys-codex"], "anosys_sdk_codex.hook_runner",
        json.dumps(data.get("notify")) if has_anosys_hook(data) else None,
        {"config": get_config_path(), "env file": get_env_path(), "state": h.STATE_FILE,
         "pending queue": h.PENDING_FILE, "log": h.LOG_FILE},
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="anosys-codex",
        description="AnoSys CLI integration for OpenAI Codex",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    p_install = subparsers.add_parser("install", help="Install AnoSys hook into ~/.codex/config.toml")
    p_install.add_argument("--api-key", help="AnoSys logs API key")
    p_install.add_argument("-y", "--yes", action="store_true", default=False, help="Automatic yes to prompts (non-interactive)")
    # Kept so old install commands still work; collection is set with `privacy`
    p_install.add_argument("--redaction", action="store_true", default=False, help=argparse.SUPPRESS)
    p_install.add_argument("--no-redaction", action="store_true", default=False, help=argparse.SUPPRESS)
    p_install.add_argument("--auto-update", dest="auto_update", action="store_true", default=None)
    p_install.add_argument("--no-auto-update", dest="auto_update", action="store_false")
    p_install.set_defaults(func=cmd_install)

    p_uninstall = subparsers.add_parser("uninstall", help="Remove AnoSys hook from ~/.codex/config.toml")
    p_uninstall.set_defaults(func=cmd_uninstall)

    p_status = subparsers.add_parser("status", help="Check hook installation status")
    p_status.set_defaults(func=cmd_status)

    add_privacy_parser(subparsers, "anosys-codex")
    add_maintenance_parsers(subparsers, _purge_paths, _doctor)

    p_run = subparsers.add_parser("run", help="Run the hook (invoked by Codex notify)")
    p_run.add_argument("rest", nargs=argparse.REMAINDER, help="Codex notification JSON")
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
