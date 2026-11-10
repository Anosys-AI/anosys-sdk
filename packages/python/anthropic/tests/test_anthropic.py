"""
Tests for anosys-sdk-anthropic Python package.

Covers:
- mapping: ANTHROPIC_KEY_MAPPING / starting indices / source tag contracts
- hooks: extract_span_info on a span shaped like the Anthropic SDK's own spans
- instrumentor: exporter only forwards spans of the Anthropic SDK's scope
"""

import json
from types import SimpleNamespace

from anosys_sdk_core.models import CLAUDE_KEY_MAPPING
from anosys_sdk_anthropic.hooks import extract_span_info
from anosys_sdk_anthropic import instrumentor
from anosys_sdk_anthropic.instrumentor import _is_anthropic_span, get_anthropic_open_telemetry_options
from anosys_sdk_anthropic.mapping import (
    ANTHROPIC_KEY_MAPPING,
    ANTHROPIC_SOURCE,
    ANTHROPIC_STARTING_INDICES,
)


def test_mapping_is_the_shared_claude_mapping():
    assert ANTHROPIC_KEY_MAPPING == CLAUDE_KEY_MAPPING
    assert ANTHROPIC_KEY_MAPPING is not CLAUDE_KEY_MAPPING
    assert ANTHROPIC_STARTING_INDICES["number"] == 8


def test_source_tag_is_pascal_case():
    assert ANTHROPIC_SOURCE == "AnthropicTelemetry"


def test_extract_span_info_from_sdk_span():
    span = {
        "name": "anthropic.messages.create",
        "context": {"trace_id": "0x1", "span_id": "0x2", "trace_state": "[]"},
        "parent_id": None,
        "start_time": "2026-10-29T10:00:00.000000Z",
        "end_time": "2026-10-29T10:00:00.250000Z",
        "status": {"status_code": "OK"},
        "attributes": {
            "server.address": "api.anthropic.com",
            "server.port": 443,
            "gen_ai.provider.name": "anthropic",
            "gen_ai.operation.name": "chat",
            "gen_ai.request.model": "claude-haiku-4-5",
            "gen_ai.request.stream": True,
            "gen_ai.usage.input_tokens": 10,
            "gen_ai.usage.output_tokens": 2,
            "gen_ai.output.messages": json.dumps([{"role": "assistant", "parts": [{"type": "text", "content": "Hi"}]}]),
        },
        "events": [],
        "resource": {"attributes": {"service.name": "svc"}},
    }
    out = extract_span_info(span)
    assert out["cvs200"] == "AnthropicTelemetry"
    assert out["cvs14"] == "api.anthropic.com"
    assert out["cvn3"] == 443
    assert out["cvb2"] is True
    assert out["gen_ai_usage_total_tokens"] == 12
    assert out["llm_output"] == "Assistant: Hi"
    assert json.loads(out["cvs199"])["name"] == "anthropic.messages.create"


def _fake_span(scope, attributes=None):
    return SimpleNamespace(
        instrumentation_scope=SimpleNamespace(name=scope) if scope else None,
        attributes=attributes or {},
    )


def test_exporter_scope_filter():
    assert _is_anthropic_span(_fake_span("com.anthropic.sdk.python"))
    assert not _is_anthropic_span(_fake_span("opentelemetry.instrumentation.fastapi"))
    assert not _is_anthropic_span(_fake_span(None))


def test_exporter_accepts_application_genai_spans():
    tool_span = {"gen_ai.operation.name": "execute_tool"}
    assert _is_anthropic_span(_fake_span("my.app", tool_span))
    # Claude Agents spans have their own exporter
    assert not _is_anthropic_span(_fake_span("anosys.claude_agents", tool_span))


def test_open_telemetry_options_follow_capture_content(monkeypatch):
    monkeypatch.setattr(instrumentor, "_capture_content", False)
    assert get_anthropic_open_telemetry_options()["traces"] == {"content_mode": "metadata_only"}
    monkeypatch.setattr(instrumentor, "_capture_content", True)
    assert get_anthropic_open_telemetry_options()["traces"] == {"content_mode": "content"}


def test_open_telemetry_options_carry_sdk_provider(monkeypatch):
    from opentelemetry.sdk.trace import TracerProvider
    provider = TracerProvider()
    monkeypatch.setattr(instrumentor.trace, "get_tracer_provider", lambda: provider)
    assert get_anthropic_open_telemetry_options()["tracer_provider"] is provider


def test_exporter_user_context_does_not_leak_session_id_to_conversation_id(monkeypatch):
    captured = []
    monkeypatch.setattr(instrumentor, "send_app_record", lambda url, data: captured.append(data))
    monkeypatch.setattr(instrumentor, "_log_api_url", "http://fake-api/ingest")
    monkeypatch.setattr(instrumentor, "_capture_level", "metadata")

    exporter = instrumentor.AnosysHttpExporter(
        get_user_context=lambda: {"session_id": "secret-session-id-4321", "token": "secret-token"}
    )
    span = SimpleNamespace(
        instrumentation_scope=SimpleNamespace(name="com.anthropic.sdk.python"),
        attributes={"gen_ai.operation.name": "chat", "gen_ai.provider.name": "anthropic"},
        to_json=lambda indent=None: json.dumps({
            "name": "anthropic.messages.create",
            "attributes": {"gen_ai.operation.name": "chat", "gen_ai.provider.name": "anthropic"},
            "status": {},
            "events": [],
            "resource": {"attributes": {"service.name": "svc"}},
        }),
    )
    exporter.export([span])
    assert len(captured) == 1
    rec = captured[0]
    # At metadata: cvs5 is dropped and session_id MUST NOT be in gen_ai_conversation_id
    assert "cvs5" not in rec
    assert rec.get("gen_ai_conversation_id") is None
    assert "secret-session-id-4321" not in json.dumps(rec)
