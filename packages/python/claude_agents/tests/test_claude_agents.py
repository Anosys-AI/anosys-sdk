"""
Tests for anosys-sdk-claude-agents Python package.

Covers:
- tracer: agent / tool / subagent / chat spans built from a simulated run
  (both the SDK's dataclass messages and plain wire-format dicts)
- tracer: errors, unfinished tool calls, content capture off
- hooks: extract_span_info source tag and Claude slots
- instrumentor: wrap_query / trace_messages pass messages through unchanged
"""

import asyncio
import json

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from anosys_sdk_claude_agents import instrumentor
from anosys_sdk_claude_agents.hooks import extract_span_info
from anosys_sdk_claude_agents.mapping import CLAUDE_AGENTS_SCOPE, CLAUDE_AGENTS_SOURCE
from anosys_sdk_claude_agents.tracer import AgentRunTracer, message_type

WIRE_RUN = [
    {"type": "system", "subtype": "init", "session_id": "sess-1", "model": "claude-opus-4-5", "tools": ["Bash", "Task"]},
    {"type": "assistant", "parent_tool_use_id": None, "message": {
        "id": "m1", "model": "claude-opus-4-5", "stop_reason": "tool_use",
        "usage": {"input_tokens": 5, "output_tokens": 3},
        "content": [
            {"type": "thinking", "thinking": "plan"},
            {"type": "tool_use", "id": "tu1", "name": "Task", "input": {"subagent_type": "explorer", "description": "look"}},
        ]}},
    {"type": "assistant", "parent_tool_use_id": "tu1", "message": {
        "id": "m2", "model": "claude-haiku-4-5",
        "content": [{"type": "tool_use", "id": "tu2", "name": "Bash", "input": {"command": "ls"}}]}},
    {"type": "user", "parent_tool_use_id": "tu1", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "tu2", "content": "a.txt", "is_error": False}]}},
    {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "tu1", "content": [{"type": "text", "text": "found a.txt"}]}]}},
    {"type": "result", "subtype": "success", "is_error": False, "num_turns": 2, "session_id": "sess-1",
     "stop_reason": "end_turn", "total_cost_usd": 0.01, "result": "Done",
     "usage": {"input_tokens": 10, "cache_read_input_tokens": 200, "cache_creation_input_tokens": 50, "output_tokens": 40}},
]


@pytest.fixture
def exporter():
    exp = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exp))
    exp.tracer = provider.get_tracer(CLAUDE_AGENTS_SCOPE)
    return exp


def _run(exporter, messages, **kwargs):
    run = AgentRunTracer(exporter.tracer, prompt="List files", options={"model": "claude-opus-4-5"}, **kwargs)
    for message in messages:
        run.on_message(message)
    run.finish()
    return {span.name: span for span in exporter.get_finished_spans()}


def test_message_type_reads_wire_and_dataclasses():
    from claude_agent_sdk.types import AssistantMessage, ResultMessage, SystemMessage
    assert message_type({"type": "result"}) == "result"
    assert message_type(AssistantMessage(content=[], model="m")) == "assistant"
    assert message_type(SystemMessage(subtype="init", data={})) == "system"
    assert message_type(ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1,
                                      is_error=False, num_turns=1, session_id="s")) == "result"


def test_span_tree(exporter):
    spans = _run(exporter, WIRE_RUN)
    root = spans["invoke_agent claude_agent"]
    task = spans["execute_tool Task"]
    bash = spans["execute_tool Bash"]
    assert task.parent.span_id == root.context.span_id
    assert bash.parent.span_id == task.context.span_id  # subagent tool nests under Task
    assert task.attributes["gen_ai.agent.name"] == "explorer"
    assert bash.attributes["gen_ai.tool.call.result"] == "a.txt"
    assert task.attributes["gen_ai.tool.call.result"] == "found a.txt"


def test_root_usage_cost_and_session(exporter):
    root = _run(exporter, WIRE_RUN)["invoke_agent claude_agent"]
    attrs = root.attributes
    assert attrs["gen_ai.conversation.id"] == "sess-1"
    assert attrs["gen_ai.usage.input_tokens"] == 260  # uncached + cache read + cache write
    assert attrs["gen_ai.usage.cache_read.input_tokens"] == 200
    assert attrs["gen_ai.usage.cache_creation.input_tokens"] == 50
    assert attrs["gen_ai.usage.cost"] == 0.01
    assert json.loads(attrs["gen_ai.output.messages"])[0]["parts"][0]["content"] == "Done"


def test_llm_spans_are_opt_in(exporter):
    assert not any(n.startswith("chat") for n in _run(exporter, WIRE_RUN))
    exporter.clear()
    spans = _run(exporter, WIRE_RUN, emit_llm_spans=True)
    assert "chat claude-opus-4-5" in spans
    assert spans["chat claude-opus-4-5"].attributes["gen_ai.usage.output_tokens"] == 3


def test_capture_content_off(exporter):
    spans = _run(exporter, WIRE_RUN, capture_content=False)
    for span in spans.values():
        assert "gen_ai.input.messages" not in span.attributes
        assert "gen_ai.tool.call.arguments" not in span.attributes
        assert "gen_ai.tool.call.result" not in span.attributes


def test_tool_error_and_unfinished_tools(exporter):
    messages = [
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "a", "name": "Bash", "input": {}},
            {"type": "tool_use", "id": "b", "name": "Read", "input": {}},
        ]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "a", "content": "boom", "is_error": True}]}},
    ]
    spans = _run(exporter, messages)
    assert spans["execute_tool Bash"].status.status_code.name == "ERROR"
    assert spans["execute_tool Read"].end_time is not None  # closed with the run


def test_extract_span_info_from_agent_span(exporter):
    root = _run(exporter, WIRE_RUN)["invoke_agent claude_agent"]
    out = extract_span_info(json.loads(root.to_json()))
    assert out["cvs200"] == CLAUDE_AGENTS_SOURCE == "ClaudeAgentsTelemetry"
    assert out["cvs19"] == "AGENT"
    assert out["cvn4"] == 200 and out["cvn5"] == 50 and out["cvn7"] == 0.01


def test_trace_messages_passes_messages_through(exporter, monkeypatch):
    monkeypatch.setattr(instrumentor, "_tracer", exporter.tracer)

    async def fake_query(*, prompt, options=None):
        for message in WIRE_RUN:
            yield message

    async def consume():
        return [m async for m in instrumentor.wrap_query(fake_query)(prompt="List files")]

    assert asyncio.run(consume()) == WIRE_RUN
    assert "invoke_agent claude_agent" in {s.name for s in exporter.get_finished_spans()}


def test_wrap_query_is_idempotent():
    async def fake_query(**kwargs):
        yield None

    wrapped = instrumentor.wrap_query(fake_query)
    assert instrumentor.wrap_query(wrapped) is wrapped


def test_http_exporter_posts_spans_with_consent(exporter, monkeypatch):
    """Regression: the exporter must not fail on every span (it referenced an undefined name)."""
    posted = []
    monkeypatch.setattr(instrumentor, "post_record", lambda url, data, timeout=5: posted.append(data))
    monkeypatch.setattr(instrumentor, "_log_api_url", "https://example.invalid/ingest")
    _run(exporter, WIRE_RUN)
    instrumentor.AnosysHttpExporter().export(exporter.get_finished_spans())
    assert posted, "no span was exported"
    assert all(p.get("cvs198", "").startswith(("full;", "metadata;")) for p in posted)
