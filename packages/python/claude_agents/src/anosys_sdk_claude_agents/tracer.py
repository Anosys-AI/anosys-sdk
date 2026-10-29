"""
Span builder for Claude Agent SDK runs.

The Agent SDK runs the model inside a Claude Code subprocess, so no in-process
instrumentor can see the API calls. Instead, AgentRunTracer reads the message
stream a run yields (system init, assistant, user/tool-result and result
messages) and turns it into OpenTelemetry GenAI semantic-convention spans:

- one ``invoke_agent`` span per run (root), carrying the session id, model,
  prompt, final result, total usage and cost;
- one ``execute_tool`` span per tool call, opened at the assistant's
  ``tool_use`` block and closed at the matching ``tool_result``; calls made by
  a subagent are nested under the ``Task``/``Agent`` tool span that launched it;
- optionally one ``chat`` span per assistant API response.

Messages are read duck-typed, so both the Python SDK's dataclasses and the
plain dicts of the wire format (also used by the TypeScript SDK) work.
"""

import json
from typing import Any, Dict, List, Optional

from opentelemetry import trace
from opentelemetry.trace import Span, SpanKind, Status, StatusCode

PROVIDER = "anthropic"
DEFAULT_AGENT_NAME = "claude_agent"
SUBAGENT_TOOLS = ("Task", "Agent")

_MESSAGE_TYPES = {
    "AssistantMessage": "assistant",
    "UserMessage": "user",
    "ResultMessage": "result",
    "StreamEvent": "stream_event",
}

_BLOCK_TYPES = {
    "TextBlock": "text",
    "ThinkingBlock": "thinking",
    "ToolUseBlock": "tool_use",
    "ToolResultBlock": "tool_result",
}


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Read a field from a dict or an object."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _json(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, default=str)


def message_type(msg: Any) -> Optional[str]:
    """Wire type of a message: system, assistant, user, result, ..."""
    msg_type = _get(msg, "type")
    if isinstance(msg_type, str):
        return msg_type
    for cls in type(msg).__mro__:
        if cls.__name__ in _MESSAGE_TYPES:
            return _MESSAGE_TYPES[cls.__name__]
        if cls.__name__ == "SystemMessage":
            return "system"
    return None


def _message_content(msg: Any) -> List[Any]:
    """Content blocks of an assistant/user message (dataclass or wire dict)."""
    inner = _get(msg, "message")
    content = _get(inner, "content") if inner is not None else _get(msg, "content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return list(content or [])


def _block_type(block: Any) -> Optional[str]:
    block_type = _get(block, "type")
    if isinstance(block_type, str):
        return block_type
    return _BLOCK_TYPES.get(type(block).__name__)


def _system_field(msg: Any, key: str) -> Any:
    """A field of a system message (Python keeps them under ``data``)."""
    value = _get(msg, key)
    if value is None:
        value = _get(_get(msg, "data"), key)
    return value


def _tool_result_text(content: Any) -> Any:
    """Plain text of a tool_result content (string or list of text blocks)."""
    if isinstance(content, list):
        texts = [_get(block, "text") for block in content if _get(block, "text")]
        if texts:
            return "\n".join(texts)
    return content


def _usage_attributes(usage: Any) -> Dict[str, Any]:
    """GenAI usage attributes from an Anthropic usage object.

    ``gen_ai.usage.input_tokens`` is the full prompt: uncached input plus cache
    reads and writes, the same meaning as OpenAI prompt tokens.
    """
    if not usage:
        return {}
    uncached = _get(usage, "input_tokens") or 0
    cache_read = _get(usage, "cache_read_input_tokens") or 0
    cache_creation = _get(usage, "cache_creation_input_tokens") or 0
    output = _get(usage, "output_tokens") or 0
    return {
        "gen_ai.usage.input_tokens": uncached + cache_read + cache_creation,
        "gen_ai.usage.output_tokens": output,
        "gen_ai.usage.cache_read.input_tokens": cache_read,
        "gen_ai.usage.cache_creation.input_tokens": cache_creation,
    }


def _output_parts(blocks: List[Any]) -> List[Dict[str, Any]]:
    """GenAI message parts for assistant content blocks."""
    parts = []
    for block in blocks:
        block_type = _block_type(block)
        if block_type == "text" and _get(block, "text"):
            parts.append({"type": "text", "content": _get(block, "text")})
        elif block_type == "thinking" and _get(block, "thinking"):
            parts.append({"type": "reasoning", "content": _get(block, "thinking")})
        elif block_type == "tool_use":
            parts.append({
                "type": "tool_call",
                "id": _get(block, "id"),
                "name": _get(block, "name"),
                "arguments": _get(block, "input"),
            })
    return parts


def _set(span: Span, attributes: Dict[str, Any]) -> None:
    for key, value in attributes.items():
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            value = _json(value)
        span.set_attribute(key, value)


class AgentRunTracer:
    """Builds the spans of one Agent SDK run from the messages it yields."""

    def __init__(
        self,
        tracer: trace.Tracer,
        prompt: Any = None,
        options: Any = None,
        agent_name: Optional[str] = None,
        capture_content: bool = True,
        emit_llm_spans: bool = False,
    ):
        self._tracer = tracer
        self._capture_content = capture_content
        self._emit_llm_spans = emit_llm_spans
        self._tool_spans: Dict[str, Span] = {}
        self._llm_message_ids: set = set()
        self._last_text: Optional[str] = None
        self._model: Optional[str] = _get(options, "model")
        self._session_id: Optional[str] = None
        self._finished = False

        self.agent_name = agent_name or DEFAULT_AGENT_NAME
        self.root = tracer.start_span(f"invoke_agent {self.agent_name}", kind=SpanKind.INTERNAL)
        _set(self.root, {
            "gen_ai.operation.name": "invoke_agent",
            "gen_ai.provider.name": PROVIDER,
            "gen_ai.agent.name": self.agent_name,
            "gen_ai.request.model": self._model,
            "anthropic.agent.permission_mode": _get(options, "permission_mode") or _get(options, "permissionMode"),
            "anthropic.agent.max_turns": _get(options, "max_turns") or _get(options, "maxTurns"),
        })
        if capture_content:
            system_prompt = _get(options, "system_prompt") or _get(options, "systemPrompt")
            if isinstance(system_prompt, str):
                _set(self.root, {"gen_ai.system_instructions": [{"type": "text", "content": system_prompt}]})
            if isinstance(prompt, str):
                _set(self.root, {"gen_ai.input.messages": [
                    {"role": "user", "parts": [{"type": "text", "content": prompt}]}
                ]})

    # ── message handling ──────────────────────────────────────────────────────

    def on_message(self, msg: Any) -> None:
        """Update spans for one message of the run. Never raises."""
        try:
            msg_type = message_type(msg)
            if msg_type == "system":
                self._on_system(msg)
            elif msg_type == "assistant":
                self._on_assistant(msg)
            elif msg_type == "user":
                self._on_user(msg)
            elif msg_type == "result":
                self._on_result(msg)
        except Exception:  # telemetry must never break the agent run
            pass

    def _on_system(self, msg: Any) -> None:
        if _get(msg, "subtype") != "init":
            return
        session_id = _system_field(msg, "session_id")
        model = _system_field(msg, "model")
        tools = _system_field(msg, "tools")
        if model and not self._model:
            self._model = model
        self._session_id = session_id or self._session_id
        _set(self.root, {
            "gen_ai.conversation.id": session_id,
            "gen_ai.request.model": self._model,
            "anthropic.agent.claude_code_version": _system_field(msg, "claude_code_version"),
        })
        if isinstance(tools, list) and tools:
            _set(self.root, {"gen_ai.tool.definitions": [
                {"type": "function", "name": t if isinstance(t, str) else _get(t, "name")} for t in tools
            ]})

    def _parent_span(self, parent_tool_use_id: Optional[str]) -> Span:
        """The span a message belongs under: the subagent's tool span, else the root."""
        if parent_tool_use_id and parent_tool_use_id in self._tool_spans:
            return self._tool_spans[parent_tool_use_id]
        return self.root

    def _on_assistant(self, msg: Any) -> None:
        blocks = _message_content(msg)
        inner = _get(msg, "message")
        parent = self._parent_span(_get(msg, "parent_tool_use_id"))
        model = _get(msg, "model") or _get(inner, "model")
        if model:
            _set(self.root, {"gen_ai.response.model": model})

        texts = [_get(b, "text") for b in blocks if _block_type(b) == "text" and _get(b, "text")]
        if texts and not _get(msg, "parent_tool_use_id"):
            self._last_text = "\n".join(texts)

        if self._emit_llm_spans:
            self._emit_llm_span(msg, inner, blocks, parent, model)

        for block in blocks:
            if _block_type(block) == "tool_use":
                self._start_tool_span(block, parent)

    def _emit_llm_span(self, msg: Any, inner: Any, blocks: List[Any], parent: Span, model: Optional[str]) -> None:
        message_id = _get(msg, "message_id") or _get(inner, "id")
        # The SDK may split one API response into several messages; record it once
        if message_id and message_id in self._llm_message_ids:
            return
        if message_id:
            self._llm_message_ids.add(message_id)
        span = self._tracer.start_span(
            f"chat {model or ''}".strip(),
            kind=SpanKind.CLIENT,
            context=trace.set_span_in_context(parent),
        )
        stop_reason = _get(msg, "stop_reason") or _get(inner, "stop_reason")
        _set(span, {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": PROVIDER,
            "gen_ai.request.model": model,
            "gen_ai.response.model": model,
            "gen_ai.response.id": message_id,
            "gen_ai.response.finish_reasons": [stop_reason] if stop_reason else None,
            **_usage_attributes(_get(msg, "usage") or _get(inner, "usage")),
        })
        if self._capture_content:
            _set(span, {"gen_ai.output.messages": [{"role": "assistant", "parts": _output_parts(blocks)}]})
        span.end()

    def _start_tool_span(self, block: Any, parent: Span) -> None:
        tool_use_id = _get(block, "id")
        name = _get(block, "name") or "unknown_tool"
        tool_input = _get(block, "input")
        span = self._tracer.start_span(
            f"execute_tool {name}",
            kind=SpanKind.INTERNAL,
            context=trace.set_span_in_context(parent),
        )
        attributes = {
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.provider.name": PROVIDER,
            "gen_ai.tool.name": name,
            "gen_ai.tool.call.id": tool_use_id,
            "gen_ai.tool.type": "extension" if name.startswith("mcp__") else "function",
            "gen_ai.conversation.id": self._session_id,
        }
        if name in SUBAGENT_TOOLS and isinstance(tool_input, dict):
            attributes["gen_ai.agent.name"] = tool_input.get("subagent_type")
            attributes["gen_ai.agent.description"] = tool_input.get("description")
        if self._capture_content and tool_input is not None:
            attributes["gen_ai.tool.call.arguments"] = tool_input
        _set(span, attributes)
        if tool_use_id:
            self._tool_spans[tool_use_id] = span
        else:
            span.end()

    def _on_user(self, msg: Any) -> None:
        for block in _message_content(msg):
            if _block_type(block) != "tool_result":
                continue
            span = self._tool_spans.pop(_get(block, "tool_use_id"), None)
            if span is None:
                continue
            content = _tool_result_text(_get(block, "content"))
            if self._capture_content and content is not None:
                _set(span, {"gen_ai.tool.call.result": content})
            if _get(block, "is_error"):
                _set(span, {"error.type": "tool_error"})
                span.set_status(Status(StatusCode.ERROR, str(content)[:500] if content else None))
            span.end()

    def _on_result(self, msg: Any) -> None:
        stop_reason = _get(msg, "stop_reason")
        _set(self.root, {
            "gen_ai.conversation.id": _get(msg, "session_id"),
            "gen_ai.response.finish_reasons": [stop_reason] if stop_reason else None,
            "gen_ai.usage.cost": _get(msg, "total_cost_usd"),
            "anthropic.agent.num_turns": _get(msg, "num_turns"),
            "anthropic.agent.duration_api_ms": _get(msg, "duration_api_ms"),
            "anthropic.agent.result_subtype": _get(msg, "subtype"),
            **_usage_attributes(_get(msg, "usage")),
        })
        result = _get(msg, "result")
        if self._capture_content and (result or self._last_text):
            _set(self.root, {"gen_ai.output.messages": [
                {"role": "assistant", "parts": [{"type": "text", "content": result or self._last_text}]}
            ]})
        if _get(msg, "is_error"):
            errors = _get(msg, "errors")
            _set(self.root, {"error.type": _get(msg, "subtype") or "agent_error"})
            self.root.set_status(Status(StatusCode.ERROR, "; ".join(errors) if errors else None))

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def finish(self, error: Optional[BaseException] = None) -> None:
        """Close any open tool spans and the root span. Idempotent."""
        if self._finished:
            return
        self._finished = True
        for span in self._tool_spans.values():
            span.end()
        self._tool_spans.clear()
        if error is not None:
            self.root.record_exception(error)
            _set(self.root, {"error.type": type(error).__name__})
            self.root.set_status(Status(StatusCode.ERROR, str(error)))
        self.root.end()
