"""
Package x level matrix for the Python application SDKs, on real OpenTelemetry spans:
off sends nothing, metadata sends no content, full sends content with a truthful
cvs198 label, enc2 applies, everything goes through the core sender, and no content
reaches the logs. (The JS suite runs the same matrix: packages/js/core/test/matrix.test.mjs.)
"""

import json
import logging

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

SECRET = "my secret prompt sk-proj-ABCDEFGHIJKLMNOPQRSTUVWX"
ATTRS = {
    "gen_ai.system": "openai",
    "gen_ai.operation.name": "chat",
    "gen_ai.request.model": "gpt-5",
    "gen_ai.usage.input_tokens": 12,
    "gen_ai.usage.output_tokens": 4,
    "gen_ai.input.messages": json.dumps([{"role": "user", "content": SECRET}]),
    "gen_ai.output.messages": json.dumps([{"role": "assistant", "content": "the answer"}]),
    "llm.input": SECRET,
}


def spans(scope="test", name="chat gpt-5", attrs=None):
    memory = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(memory))
    with provider.get_tracer(scope).start_as_current_span(name, attributes=attrs or ATTRS):
        pass
    return memory.get_finished_spans()


def _module(name):
    return pytest.importorskip(name)


CASES = [
    ("anosys_sdk_openai.instrumentor", "OpenAI", lambda: spans()),
    ("anosys_sdk_openai.instrumentor", "OpenRouter via OpenAI SDK",
     lambda: spans(name="chat openrouter", attrs={**ATTRS, "server.address": "openrouter.ai",
                                                   "gen_ai.request.model": "anthropic/claude-sonnet-5-5"})),
    ("anosys_sdk_openai_agents.processor", "OpenAI Agents (OTel path)", lambda: spans()),
    ("anosys_sdk_anthropic.instrumentor", "Anthropic",
     lambda: spans(scope="anthropic", attrs={**ATTRS, "gen_ai.system": "anthropic", "gen_ai.provider.name": "anthropic"})),
]
LEVELS = ["off", "metadata", "full", "full+enc2"]


@pytest.mark.parametrize("module_name,vendor,make", CASES, ids=[c[1] for c in CASES])
@pytest.mark.parametrize("level", LEVELS)
def test_exporter_matrix(module_name, vendor, make, level, monkeypatch, caplog):
    mod = _module(module_name)
    posted = []
    monkeypatch.setattr(mod, "send_app_record", lambda url, rec: posted.append(rec))
    monkeypatch.setattr(mod, "_log_api_url", "https://ingest.example")
    monkeypatch.setattr(mod, "_capture_level", level.split("+")[0])
    if level.endswith("enc2"):
        monkeypatch.setenv("ANOSYS_ENCRYPTION_KEY", "pass")
        monkeypatch.setenv("ANOSYS_ENCRYPTION_SALT", "ws")
    else:
        monkeypatch.delenv("ANOSYS_ENCRYPTION_KEY", raising=False)

    with caplog.at_level(logging.DEBUG):
        mod.AnosysHttpExporter().export(make())
    assert SECRET not in caplog.text and "the answer" not in caplog.text

    if level == "off":
        assert posted == []
        return
    assert len(posted) == 1, f"{vendor}: expected one record"
    rec = posted[0]
    body = json.dumps(rec)
    assert "consent" not in rec
    if level == "metadata":
        assert rec["cvs198"] == "metadata;app"
        assert "secret prompt" not in body and "the answer" not in body and "sk-proj" not in body
        assert rec.get("otel_trace_id") and isinstance(rec.get("cvn1"), (int, float))
    elif level == "full":
        assert rec["cvs198"] == "full;app" and "secret prompt" in body
    else:
        assert rec["cvs198"] == "full;app" and "enc2:" in body and "secret prompt" not in body


@pytest.mark.parametrize("level,expect", [("off", None), ("metadata", False), ("full", True)])
def test_decorators_matrix(level, expect, monkeypatch, tmp_path):
    from anosys_sdk_core import decorators
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANOSYS_COLLECTION_LEVEL", level)
    monkeypatch.delenv("ANOSYS_ENCRYPTION_KEY", raising=False)
    posted = []
    monkeypatch.setattr(decorators, "send_app_record", lambda url, rec: posted.append(rec))
    monkeypatch.setattr(decorators, "_log_api_url", "https://ingest.example")

    @decorators.anosys_logger("unit")
    def answer(q):
        return f"answer to {q}"

    assert answer(SECRET) == f"answer to {SECRET}"
    decorators.anosys_raw_logger({"note": SECRET, "count": 3})
    if expect is None:
        assert posted == []
        return
    assert len(posted) == 2 and all(r["cvs198"] == f"{level};app" for r in posted)
    assert ("secret prompt" in json.dumps(posted)) is expect


def test_client_matrix(monkeypatch, tmp_path):
    from anosys_sdk_core import client as client_mod
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANOSYS_COLLECTION_LEVEL", "metadata")
    sent = []
    monkeypatch.setattr(client_mod, "post_record", lambda url, rec, timeout=5: sent.append(rec))
    client_mod.AnosysClient(api_url="https://ingest.example").send({"llm_input": SECRET, "otel_name": "x", "n": 1})
    assert sent == [{"otel_name": "x", "n": 1, "cvs198": "metadata;app"}]
