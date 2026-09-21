"""
Unit tests for anosys-antigravity package.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from anosys_sdk_antigravity.constants import HOOK_NAME, INTEGRATION_VERSION
from anosys_sdk_antigravity.hook_runner import (
    clear_pending_records,
    load_pending_records,
    load_state,
    save_pending_records,
    save_state,
)
from anosys_sdk_antigravity.installer import (
    has_anosys_hook,
    load_json,
    remove_env_config,
    remove_hooks_config,
    update_env_config,
    update_hooks_config,
    validate_api_key,
)
from anosys_sdk_antigravity.mapper import extract_tool_details, transform_antigravity_turn
from anosys_sdk_antigravity.transcript import (
    build_turn,
    extract_metadata_fields,
    extract_settings_change,
    extract_user_request,
    iso_to_ms,
    parse_transcript,
)


def test_iso_to_ms():
    assert iso_to_ms("2026-09-21T19:57:09Z") > 0
    assert iso_to_ms("2026-09-21T19:57:09+03:00") > 0
    assert iso_to_ms("") == 0
    assert iso_to_ms("invalid") == 0


def test_extract_user_request():
    content = (
        "<USER_REQUEST>\n"
        "check how arize add logs tracing and implement similar for us\n"
        "</USER_REQUEST>\n"
        "<ADDITIONAL_METADATA>\n"
        "The current local time is: 2026-09-21T19:57:09+03:00.\n"
        "</ADDITIONAL_METADATA>"
    )
    req = extract_user_request(content)
    assert req == "check how arize add logs tracing and implement similar for us"

    # Fallback when tag is missing
    fallback = extract_user_request("Direct user prompt without tags")
    assert fallback == "Direct user prompt without tags"


def test_extract_metadata_fields():
    content = (
        "<USER_REQUEST>Fix bug</USER_REQUEST>\n"
        "<ADDITIONAL_METADATA>\n"
        "The current local time is: 2026-09-21T19:57:09+03:00.\n\n"
        "The user's current state is as follows:\n"
        "Active Document: c:\\AnoSys\\anosys-sdk\\packages\\python\\claude_code\\src\\anosys_sdk_claude_code\\mapper.py (LANGUAGE_PYTHON)\n"
        "Cursor is on line: 541\n"
        "</ADDITIONAL_METADATA>"
    )
    meta = extract_metadata_fields(content)
    assert meta["active_document"] == "c:\\AnoSys\\anosys-sdk\\packages\\python\\claude_code\\src\\anosys_sdk_claude_code\\mapper.py"
    assert meta["active_document_language"] == "LANGUAGE_PYTHON"
    assert meta["cursor_line"] == 541
    assert meta["client_timestamp_iso"] == "2026-09-21T19:57:09+03:00"


def test_extract_settings_change():
    content = (
        "<USER_SETTINGS_CHANGE>\n"
        "The user changed setting `Model Selection` from None to Gemini 3.8 Flash (High). No need to comment on this change.\n"
        "</USER_SETTINGS_CHANGE>"
    )
    settings = extract_settings_change(content)
    assert settings["model_name"] == "Gemini 3.8 Flash (High)"
    assert "Model Selection" in settings["user_settings_change"]


def test_build_turn_and_parse_transcript(tmp_path: Path):
    transcript_file = tmp_path / "transcript_full.jsonl"
    records = [
        {
            "step_index": 1,
            "type": "USER_INPUT",
            "source": "USER_EXPLICIT",
            "created_at": "2026-09-21T19:57:00Z",
            "content": (
                "<USER_REQUEST>Run tests and fix issues</USER_REQUEST>\n"
                "<ADDITIONAL_METADATA>\n"
                "The current local time is: 2026-09-21T19:57:00+03:00.\n"
                "Active Document: /workspace/main.py (LANGUAGE_PYTHON)\n"
                "Cursor is on line: 42\n"
                "</ADDITIONAL_METADATA>\n"
                "<USER_SETTINGS_CHANGE>\n"
                "The user changed setting `Model Selection` from None to gemini-2.5-pro.\n"
                "</USER_SETTINGS_CHANGE>"
            ),
        },
        {
            "step_index": 2,
            "type": "PLANNER_RESPONSE",
            "created_at": "2026-09-21T19:57:02Z",
            "content": "I will run the test command now.",
            "thinking": "Analyzing the workspace layout before running pytest.",
            "tool_calls": [
                {
                    "name": "run_command",
                    "args": {"CommandLine": "pytest tests/ -v"},
                }
            ],
        },
        {
            "step_index": 3,
            "type": "TOOL_RESULT",
            "created_at": "2026-09-21T19:57:03Z",
            "status": "DONE",
            "content": "Created At: 2026-09-21T19:57:02Z\nCompleted At: 2026-09-21T19:57:05Z\nAll 10 tests passed.",
        },
        {
            "step_index": 4,
            "type": "PLANNER_RESPONSE",
            "created_at": "2026-09-21T19:57:06Z",
            "content": "All tests passed successfully!",
            "thinking": "",
            "tool_calls": [],
        },
    ]

    with open(transcript_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    turns = parse_transcript(transcript_file)
    assert len(turns) == 1
    t = turns[0]
    assert t["user_input"] == "Run tests and fix issues"
    assert t["final_response"] == "All tests passed successfully!"
    assert t["model_name"] == "gemini-2.5-pro"
    assert t["active_document"] == "/workspace/main.py"
    assert t["cursor_line"] == 42
    assert t["has_thinking"] is True
    assert len(t["llm_steps"]) == 2
    assert len(t["tool_steps"]) == 1
    tool = t["tool_steps"][0]
    assert tool["name"] == "run_command"
    assert tool["args"]["CommandLine"] == "pytest tests/ -v"
    assert tool["duration_ms"] == 3000


def test_extract_tool_details():
    tool_steps = [
        {
            "name": "run_command",
            "args": {"CommandLine": "npm test"},
            "output": "PASS",
            "duration_ms": 1200,
        },
        {
            "name": "write_to_file",
            "args": {"TargetFile": "/app/index.js"},
            "output": "written",
            "duration_ms": 50,
        },
        {
            "name": "view_file",
            "args": {"AbsolutePath": "/app/README.md"},
            "output": "content",
            "duration_ms": 30,
        },
        {
            "name": "search_web",
            "args": {"query": "gemini api docs"},
            "output": "results",
            "duration_ms": 800,
        },
        {
            "name": "browser_subagent",
            "args": {"TaskName": "Verify login flow"},
            "output": "success",
            "duration_ms": 5000,
        },
    ]

    details = extract_tool_details(tool_steps)
    assert details["tool_count"] == 5
    assert "npm test" in details["commands"]
    assert "/app/index.js" in details["written_paths"]
    assert "/app/README.md" in details["viewed_paths"]
    assert "gemini api docs" in details["searched_queries"]
    assert "Verify login flow" in details["subagents_spawned"]
    assert details["tool_duration_ms"] == 7080


def test_transform_antigravity_turn():
    turn = {
        "user_input": "Deploy the application",
        "final_response": "Deployed to production.",
        "model_name": "gemini-2.5-pro",
        "start_ms": 1700000000000,
        "end_ms": 1700000010000,
        "active_document": "/src/deploy.py",
        "active_document_language": "LANGUAGE_PYTHON",
        "cursor_line": 100,
        "client_timestamp_iso": "2026-09-21T19:57:09+03:00",
        "user_settings_change": "Changed model",
        "user_source": "USER_EXPLICIT",
        "has_thinking": True,
        "max_step_index": 15,
        "step_count": 8,
        "llm_steps": [{"content": "Deploying...", "thinking": "plan", "start_ms": 1700000000000, "end_ms": 1700000002000}],
        "tool_steps": [
            {
                "name": "run_command",
                "args": {"CommandLine": "kubectl apply -f k8s/"},
                "output": "deployment created",
                "duration_ms": 3500,
            }
        ],
    }
    hook_meta = {
        "workspacePaths": ["/Users/dev/my-project"],
        "transcriptPath": "/Users/dev/my-project/.gemini/antigravity/transcript.jsonl",
        "artifactDirectoryPath": "/Users/dev/my-project/.gemini/antigravity/artifacts",
        "terminationReason": "model_stop",
        "fullyIdle": True,
        "executionNum": 1,
    }

    payload = transform_antigravity_turn(
        turn=turn,
        session_id="conv-12345",
        turn_id="conv-12345_0",
        hook_metadata=hook_meta,
        redact=False,
    )

    # Named variables
    assert payload["session_id"] == "conv-12345"
    assert payload["sessionId"] == "conv-12345"
    assert payload["uuid"] == "conv-12345_0"
    assert payload["event_type"] == "antigravity_turn"
    assert payload["event_source_name"] == "antigravity"
    assert payload["user_prompt"] == "Deploy the application"
    assert payload["assistant_text"] == "Deployed to production."
    assert payload["model"] == "gemini-2.5-pro"
    assert payload["model_provider"] == "google"
    assert payload["cwd"] == "/Users/dev/my-project"
    assert payload["project"] == "my-project"
    assert payload["active_document"] == "/src/deploy.py"
    assert payload["active_document_language"] == "LANGUAGE_PYTHON"
    assert payload["cursor_line"] == 100
    assert payload["duration_ms"] == 10000
    assert payload["tool_count"] == 1
    assert payload["has_thinking"] is True
    assert payload["fully_idle"] is True
    assert payload["execution_num"] == 1
    assert payload["integration_version"] == INTEGRATION_VERSION

    # CV columns (CC pixel)
    assert payload["cvs1"] == "conv-12345"
    assert payload["cvs2"] == "my-project"
    assert payload["cvs4"] == "Deploy the application"
    assert payload["cvs5"] == "Deployed to production."
    assert payload["cvs6"] == "model_stop"
    assert payload["cvs9"] == "gemini-2.5-pro"
    assert payload["cvs12"] == "/Users/dev/my-project"
    assert payload["cvs17"] == "google"
    assert payload["cvs70"] == "/src/deploy.py"
    assert payload["cvs71"] == "LANGUAGE_PYTHON"
    assert payload["cvn25"] == 100
    assert payload["cvn6"] == 10000
    assert payload["cvn41"] == 1
    assert payload["cvb2"] is True
    assert payload["cvs200"] == "AntigravityHook"
    assert "kubectl apply" in payload["cvs90"]


def test_transform_antigravity_turn_redaction():
    turn = {
        "user_input": "Secret token is ABC123XYZ",
        "final_response": "Processed secret token.",
        "model_name": "gemini-2.5-pro",
        "start_ms": 1000,
        "end_ms": 2000,
        "tool_steps": [
            {
                "name": "run_command",
                "args": {"CommandLine": "curl -H 'Auth: Bearer ABC123XYZ'"},
                "output": "Sensitive output with ABC123XYZ",
                "duration_ms": 500,
            }
        ],
    }

    payload = transform_antigravity_turn(
        turn=turn,
        session_id="conv-sec",
        turn_id="conv-sec_0",
        hook_metadata={"workspacePaths": ["/proj"]},
        redact=True,
    )

    assert payload["user_prompt"] == "[REDACTED]"
    assert payload["assistant_text"] == "[REDACTED]"
    assert payload["cvs4"] == "[REDACTED]"
    assert payload["cvs5"] == "[REDACTED]"
    assert "ABC123XYZ" not in payload["cvs199"]


def test_installer_hooks_config_lifecycle(tmp_path: Path):
    hooks_file = tmp_path / "hooks.json"

    # Initially empty
    assert not hooks_file.exists()
    assert has_anosys_hook({}) is False

    # Pre-existing third-party hook
    initial_data = {
        "existing-linter": {
            "PostToolUse": [{"type": "command", "command": "./lint.sh"}]
        }
    }
    hooks_file.write_text(json.dumps(initial_data, indent=2), encoding="utf-8")

    # Install
    update_hooks_config(hooks_file, command="anosys-antigravity run")
    data = load_json(hooks_file)

    assert has_anosys_hook(data) is True
    assert "existing-linter" in data  # preserved
    assert HOOK_NAME in data
    assert "PreInvocation" in data[HOOK_NAME]
    assert "Stop" in data[HOOK_NAME]
    assert data[HOOK_NAME]["PreInvocation"][0]["command"] == "anosys-antigravity run pre_invocation"
    assert data[HOOK_NAME]["Stop"][0]["command"] == "anosys-antigravity run stop"

    # Uninstall
    removed = remove_hooks_config(hooks_file)
    assert removed is True
    data_after = load_json(hooks_file)
    assert has_anosys_hook(data_after) is False
    assert "existing-linter" in data_after  # still preserved


def test_installer_env_lifecycle(tmp_path: Path):
    env_file = tmp_path / "anosys-env.json"
    update_env_config(env_file, api_key="test-api-key", endpoint_url="https://api.test/ingest", redaction=True)

    data = load_json(env_file)
    assert data["ANOSYS_HOOK_APIKEY"] == "test-api-key"
    assert data["ANOSYS_HOOK_ENDPOINT_URL"] == "https://api.test/ingest"
    assert data["REDACTION"] == "true"

    removed = remove_env_config(env_file)
    assert removed is True
    assert not env_file.exists()


def test_hook_runner_state(tmp_path: Path, monkeypatch):
    import anosys_sdk_antigravity.hook_runner as hr
    monkeypatch.setattr(hr, "STATE_DIR", tmp_path)

    state = load_state("conv-xyz")
    assert state["last_emitted_turn"] == -1

    state["last_emitted_turn"] = 2
    state["processed_turns"] = ["conv-xyz_0", "conv-xyz_1", "conv-xyz_2"]
    save_state("conv-xyz", state)

    reloaded = load_state("conv-xyz")
    assert reloaded["last_emitted_turn"] == 2
    assert len(reloaded["processed_turns"]) == 3


def test_hook_runner_pending_records(tmp_path: Path, monkeypatch):
    import anosys_sdk_antigravity.hook_runner as hr
    monkeypatch.setattr(hr, "PENDING_FILE", tmp_path / "pending_records.jsonl")

    records = [{"turn_id": "t1", "prompt": "p1"}, {"turn_id": "t2", "prompt": "p2"}]
    save_pending_records(records)

    loaded = load_pending_records()
    assert len(loaded) == 2
    assert loaded[0]["turn_id"] == "t1"

    clear_pending_records()
    assert len(load_pending_records()) == 0


def test_validate_api_key_mock():
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps({"apiUrl": "https://api.anosys.ai/cc/ingestion"}).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        assert validate_api_key("valid_key", "cc") is True
        assert validate_api_key("valid_key", "antigravity") is True
        assert validate_api_key("valid_key", "otel") is False


def test_cli_install_with_api_key_flag(tmp_path: Path, monkeypatch):
    from anosys_sdk_antigravity.cli import main

    hooks_file = tmp_path / "hooks.json"
    env_file = tmp_path / "anosys-env.json"

    monkeypatch.setattr("anosys_sdk_antigravity.cli.get_hooks_path", lambda workspace=False: hooks_file)
    monkeypatch.setattr("anosys_sdk_antigravity.cli.get_env_path", lambda workspace=False: env_file)
    monkeypatch.setattr("anosys_sdk_antigravity.cli.validate_api_key", lambda key, t: True)

    main(["install", "--api-key", "my-secret-key", "-y"])

    assert hooks_file.is_file()
    assert env_file.is_file()
    env_data = json.loads(env_file.read_text(encoding="utf-8"))
    assert env_data["ANOSYS_HOOK_APIKEY"] == "my-secret-key"


def test_cli_install_with_api_key_positional(tmp_path: Path, monkeypatch):
    from anosys_sdk_antigravity.cli import main

    hooks_file = tmp_path / "hooks.json"
    env_file = tmp_path / "anosys-env.json"

    monkeypatch.setattr("anosys_sdk_antigravity.cli.get_hooks_path", lambda workspace=False: hooks_file)
    monkeypatch.setattr("anosys_sdk_antigravity.cli.get_env_path", lambda workspace=False: env_file)
    monkeypatch.setattr("anosys_sdk_antigravity.cli.validate_api_key", lambda key, t: True)

    main(["install", "my-positional-key", "-y"])

    assert hooks_file.is_file()
    assert env_file.is_file()
    env_data = json.loads(env_file.read_text(encoding="utf-8"))
    assert env_data["ANOSYS_HOOK_APIKEY"] == "my-positional-key"

