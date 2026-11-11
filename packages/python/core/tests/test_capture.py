"""Tests for unified capture control of the application SDKs (anosys_sdk_core.capture)."""

import json

import pytest

from anosys_sdk_core.capture import (
    app_consent_value, finalize_app_record, prepare_app_record, resolve_app_level, strip_content,
)
from anosys_sdk_core.privacy import FULL, METADATA, OFF

SPAN = {
    "otel_trace_id": "t1", "otel_name": "chat", "gen_ai_request_model": "gpt-5",
    "gen_ai_usage_input_tokens": 12, "otel_duration_ms": 3.5, "cvb2": False,
    "llm_input": "my secret prompt", "llm_output": "answer",
    "gen_ai_input_messages": [{"role": "user", "content": "hi"}],
    "cvs18": json.dumps({"gen_ai.prompt": "hi"}), "cvs199": "{raw span}", "cvs105": "dynamic attribute text",
    "cvs200": "openAI_Python_Telemetry", "consent": "stale",
}


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    for var in ("ANOSYS_DISABLE", "ANOSYS_COLLECTION_LEVEL", "ANOSYS_ENCRYPTION_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_default_is_full_and_never_reads_the_consent_file(monkeypatch, tmp_path):
    monkeypatch.setenv("ANOSYS_CONSENT_FILE", str(tmp_path / "missing.json"))
    assert resolve_app_level() == (FULL, "default")


def test_precedence(monkeypatch, isolated):
    monkeypatch.setenv("ANOSYS_COLLECTION_LEVEL", "metadata")
    assert resolve_app_level() == (METADATA, "ANOSYS_COLLECTION_LEVEL")
    assert resolve_app_level(True) == (FULL, "argument")          # argument beats env
    assert resolve_app_level(False) == (METADATA, "argument")
    assert resolve_app_level("off") == (OFF, "argument")
    (isolated / ".anosys").write_text("level=metadata\n")
    assert resolve_app_level(True) == (METADATA, ".anosys")       # project file is a ceiling
    assert resolve_app_level("off") == (OFF, "argument")          # ... that only lowers
    monkeypatch.setenv("ANOSYS_DISABLE", "1")
    assert resolve_app_level(True) == (OFF, "ANOSYS_DISABLE")


def test_metadata_keeps_only_numbers_flags_and_allowlisted_strings():
    out = finalize_app_record(SPAN, METADATA)
    assert out == {
        "otel_trace_id": "t1", "otel_name": "chat", "gen_ai_request_model": "gpt-5",
        "gen_ai_usage_input_tokens": 12, "otel_duration_ms": 3.5, "cvb2": False,
        "cvs200": "openAI_Python_Telemetry", "cvs198": "metadata;app",
    }
    assert "secret" not in json.dumps(out) and "dynamic" not in json.dumps(out)


def test_extra_allowed_columns():
    out = finalize_app_record({"cvs78": "triage_agent", "llm_input": "x"}, METADATA, ["cvs78"])
    assert out == {"cvs78": "triage_agent", "cvs198": "metadata;app"}


def test_full_and_off():
    full = finalize_app_record(SPAN, FULL)
    assert full["llm_input"] == "my secret prompt" and full["cvs198"] == "full;app"
    assert "consent" not in full
    assert finalize_app_record(SPAN, OFF) is None
    assert prepare_app_record(SPAN, OFF) is None


def test_app_label_never_claims_policy_acceptance():
    for level in (FULL, METADATA):
        assert app_consent_value(level).endswith(";app")


def test_prepare_encrypts_after_filtering(monkeypatch):
    monkeypatch.setenv("ANOSYS_ENCRYPTION_KEY", "pass")
    monkeypatch.setenv("ANOSYS_ENCRYPTION_SALT", "ws")
    out = prepare_app_record(SPAN, FULL)
    assert out["llm_input"].startswith("enc2:") and out["cvs198"] == "full;app"


def test_strip_content_drops_objects_and_none():
    assert strip_content({"a": None, "b": {"x": 1}, "c": 1}) == {"c": 1}
