"""
OpenTelemetry GenAI semantic-convention span extraction for AnoSys.

Turns a span that follows the OTel GenAI conventions (``gen_ai.*`` attributes,
parts-based ``gen_ai.input.messages`` / ``gen_ai.output.messages``) into the
AnoSys payload, keyed by CVS variables through ``reassign()``.

The Anthropic client SDK emits these spans natively, and the AnoSys Claude
Agents integration emits them for agent and tool spans, so both share this
extractor and land in the same columns as the OpenAI integrations.

The input is the dict produced by ``ReadableSpan.to_json()`` (Python) or the
equivalent structure built by the JS packages: ``name``, ``context``,
``parent_id``, ``start_time``, ``end_time``, ``status``, ``attributes``
(flat), ``events`` and ``resource``.
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from anosys_sdk_core.models import CLAUDE_KEY_MAPPING, CLAUDE_STARTING_INDICES
from anosys_sdk_core.util.batching import assign, reassign
from anosys_sdk_core.util.json import to_str_or_none

# gen_ai.operation.name -> AnoSys span kind (gen_ai.span.kind / otel_kind)
OPERATION_SPAN_KINDS = {
    "chat": "LLM",
    "text_completion": "LLM",
    "generate_content": "LLM",
    "embeddings": "EMBEDDING",
    "invoke_agent": "AGENT",
    "create_agent": "AGENT",
    "execute_tool": "TOOL",
}

# Request parameters copied 1:1 to gen_ai.request.* (and llm_invocation_parameters)
REQUEST_PARAMETERS = (
    "max_tokens",
    "temperature",
    "top_p",
    "top_k",
    "stop_sequences",
    "seed",
    "frequency_penalty",
    "presence_penalty",
    "choice.count",
    "tool_choice",
)

_STATUS_CODES = {0: "UNSET", 1: "OK", 2: "ERROR"}


def _to_timestamp(dt_str: Optional[str]) -> Optional[int]:
    """Convert ISO datetime string to milliseconds timestamp."""
    if not dt_str:
        return None
    try:
        return int(datetime.fromisoformat(str(dt_str).replace("Z", "+00:00")).timestamp() * 1000)
    except (ValueError, AttributeError):
        return None


def _parse_json(value: Any) -> Any:
    """Parse JSON-encoded attribute values (messages, arguments, results)."""
    if isinstance(value, str) and value.strip().startswith(("{", "[")):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _to_number(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _compact(value: Any) -> Any:
    """Compact JSON for dicts/lists (same text as JSON.stringify in the JS SDK)."""
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"), default=str)
    return value


def _part_text(part: Dict[str, Any]) -> Optional[str]:
    """Readable text for one message part."""
    part_type = part.get("type")
    if part_type in ("text", "reasoning"):
        content = part.get("content")
        return f"[Thinking] {content}" if part_type == "reasoning" and content else content
    if part_type == "tool_call":
        args_text = _compact(part.get("arguments"))
        return f"[Tool Call: {part.get('name')}] {args_text or ''}".rstrip()
    if part_type == "tool_call_response":
        response_text = _compact(part.get("response"))
        return f"[Tool Result] {response_text or ''}".rstrip()
    content = part.get("content")
    return content if isinstance(content, str) else None


def flatten_messages(messages: Any) -> Optional[str]:
    """
    Flatten GenAI messages into a readable string ("Role: text" blocks).

    Accepts the parts-based convention (``{"role", "parts": [...]}``) and the
    classic ``{"role", "content"}`` shape.
    """
    messages = _parse_json(messages)
    if not messages:
        return None
    if isinstance(messages, str):
        return messages
    if not isinstance(messages, list):
        return str(messages)

    blocks = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        parts = message.get("parts")
        if isinstance(parts, list):
            texts = [t for t in (_part_text(p) for p in parts if isinstance(p, dict)) if t]
            text = "\n".join(texts)
        else:
            content = message.get("content")
            text = content if isinstance(content, str) else to_str_or_none(content)
        if text:
            label = f"{role.capitalize()}: " if role else ""
            blocks.append(f"{label}{text}")
    return "\n\n".join(blocks) if blocks else None


def _system_text(system_instructions: Any) -> Optional[str]:
    """Plain text of gen_ai.system_instructions (a list of parts or a string)."""
    system_instructions = _parse_json(system_instructions)
    if isinstance(system_instructions, list):
        texts = [p.get("content") for p in system_instructions if isinstance(p, dict) and p.get("content")]
        return "\n".join(texts) if texts else None
    return to_str_or_none(system_instructions)


def _has_reasoning(messages: Any) -> bool:
    messages = _parse_json(messages)
    if not isinstance(messages, list):
        return False
    for message in messages:
        parts = message.get("parts") if isinstance(message, dict) else None
        if isinstance(parts, list) and any(isinstance(p, dict) and p.get("type") == "reasoning" for p in parts):
            return True
    return False


def extract_genai_span_info(
    span: Dict[str, Any],
    from_source: str,
    provider: str = "anthropic",
    key_mapping: Optional[Dict[str, str]] = None,
    starting_indices: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """
    Extract and transform a GenAI semantic-convention span into AnoSys format.

    Args:
        span: Span dictionary (``ReadableSpan.to_json()`` shape)
        from_source: Source tag stored in cvs200
        provider: Fallback for gen_ai.system / gen_ai.provider.name
        key_mapping: Key-to-CVS mapping (default: CLAUDE_KEY_MAPPING)
        starting_indices: Dynamic slot indices (default: CLAUDE_STARTING_INDICES)

    Returns:
        Transformed dictionary ready for the AnoSys API
    """
    variables: Dict[str, Any] = {}
    key_to_cvs = (key_mapping or CLAUDE_KEY_MAPPING).copy()
    attributes: Dict[str, Any] = dict(span.get("attributes") or {})
    resource_attrs: Dict[str, Any] = (span.get("resource") or {}).get("attributes") or {}
    context = span.get("context") or {}

    # Top-level metadata
    assign(variables, "otel_record_type", "AnoSys Trace")
    assign(variables, "custom_mapping", json.dumps(key_to_cvs, indent=4))
    assign(variables, "otel_observed_timestamp", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))
    assign(variables, "name", to_str_or_none(span.get("name")))
    assign(variables, "trace_id", to_str_or_none(context.get("trace_id")))
    assign(variables, "span_id", to_str_or_none(context.get("span_id")))
    assign(variables, "trace_state", to_str_or_none(context.get("trace_state")) or None)
    assign(variables, "parent_id", to_str_or_none(span.get("parent_id")))
    assign(variables, "start_time", to_str_or_none(span.get("start_time")))
    assign(variables, "end_time", to_str_or_none(span.get("end_time")))

    start_ts = _to_timestamp(span.get("start_time"))
    end_ts = _to_timestamp(span.get("end_time"))
    assign(variables, "cvn1", start_ts)
    assign(variables, "cvn2", end_ts)
    if start_ts is not None and end_ts is not None:
        assign(variables, "otel_duration_ms", end_ts - start_ts)

    # Status
    status = span.get("status") or {}
    if status:
        assign(variables, "status", to_str_or_none(status))
        status_code = status.get("status_code")
        if status_code is not None:
            assign(variables, "status_code", _STATUS_CODES.get(status_code, str(status_code)))

    # Gen AI - System & operation
    provider_name = attributes.get("gen_ai.provider.name") or attributes.get("gen_ai.system") or provider
    operation = attributes.get("gen_ai.operation.name")
    assign(variables, "gen_ai.system", provider_name)
    assign(variables, "gen_ai.provider.name", provider_name)
    assign(variables, "gen_ai.operation.name", to_str_or_none(operation))

    kind_val = OPERATION_SPAN_KINDS.get(operation) if operation else None
    assign(variables, "gen_ai.span.kind", kind_val)
    assign(variables, "kind", kind_val)

    assign(variables, "server.address", attributes.get("server.address") or resource_attrs.get("server.address"))
    assign(variables, "server.port", attributes.get("server.port") or resource_attrs.get("server.port"))
    assign(variables, "error.type", to_str_or_none(attributes.get("error.type")))
    assign(variables, "service.name", resource_attrs.get("service.name") or "unknown_service")
    assign(variables, "attributes", attributes)

    # Request configuration
    model = attributes.get("gen_ai.request.model")
    assign(variables, "gen_ai.request.model", to_str_or_none(model))
    invocation_params: Dict[str, Any] = {}
    if model:
        invocation_params["model"] = model
    for param in REQUEST_PARAMETERS:
        value = attributes.get(f"gen_ai.request.{param}")
        if value is None:
            continue
        value = _parse_json(value)
        invocation_params[param] = value
        assign(variables, f"gen_ai.request.{param}", to_str_or_none(value) if param == "tool_choice" else value)

    # Response
    response_id = attributes.get("gen_ai.response.id")
    finish_reasons = _parse_json(attributes.get("gen_ai.response.finish_reasons"))
    if not finish_reasons and attributes.get("anthropic.message.stop_reason"):
        finish_reasons = [attributes["anthropic.message.stop_reason"]]
    if isinstance(finish_reasons, str):
        finish_reasons = [finish_reasons]
    assign(variables, "gen_ai.response.model", to_str_or_none(attributes.get("gen_ai.response.model")))
    assign(variables, "gen_ai.response.id", to_str_or_none(response_id))
    assign(variables, "gen_ai.response.finish_reasons", list(finish_reasons) if finish_reasons else None)
    assign(variables, "gen_ai.output.type", to_str_or_none(attributes.get("gen_ai.output.type")))
    assign(variables, "resp_id", to_str_or_none(response_id))

    # Usage. gen_ai.usage.input_tokens is the full prompt (cache reads/writes
    # included), matching the OpenAI meaning of prompt tokens.
    input_tokens = _to_number(attributes.get("gen_ai.usage.input_tokens"))
    output_tokens = _to_number(attributes.get("gen_ai.usage.output_tokens"))
    total_tokens = _to_number(attributes.get("gen_ai.usage.total_tokens"))
    cache_read = _to_number(attributes.get("gen_ai.usage.cache_read.input_tokens"))
    cache_creation = _to_number(
        attributes.get("gen_ai.usage.cache_creation.input_tokens")
        if attributes.get("gen_ai.usage.cache_creation.input_tokens") is not None
        else attributes.get("gen_ai.usage.cache_write.input_tokens")
    )
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    reasoning_tokens = _to_number(attributes.get("gen_ai.usage.reasoning.output_tokens"))
    cost = _to_number(attributes.get("gen_ai.usage.cost"))

    assign(variables, "gen_ai.usage.input_tokens", input_tokens)
    assign(variables, "gen_ai.usage.output_tokens", output_tokens)
    assign(variables, "gen_ai.usage.total_tokens", total_tokens)
    assign(variables, "gen_ai.usage.cache_read.input_tokens", cache_read)
    assign(variables, "gen_ai.usage.cache_creation.input_tokens", cache_creation)
    assign(variables, "gen_ai.usage.cost", cost)

    token_count = {
        k: v
        for k, v in (
            ("input_tokens", input_tokens),
            ("output_tokens", output_tokens),
            ("total_tokens", total_tokens),
            ("cache_read_input_tokens", cache_read),
            ("cache_creation_input_tokens", cache_creation),
            ("reasoning_output_tokens", reasoning_tokens),
        )
        if v is not None
    }
    assign(variables, "llm_token_count", token_count or None)

    # Content
    input_messages = _parse_json(attributes.get("gen_ai.input.messages"))
    output_messages = _parse_json(attributes.get("gen_ai.output.messages"))
    system_instructions = _parse_json(attributes.get("gen_ai.system_instructions"))
    tool_definitions = _parse_json(attributes.get("gen_ai.tool.definitions"))
    assign(variables, "gen_ai.input.messages", input_messages)
    assign(variables, "gen_ai.output.messages", output_messages)
    assign(variables, "gen_ai.system_instructions", system_instructions)
    assign(variables, "gen_ai.tool.definitions", tool_definitions)
    if _has_reasoning(output_messages):
        assign(variables, "has_thinking", True)

    # Agents & Tools
    assign(variables, "gen_ai.agent.id", to_str_or_none(attributes.get("gen_ai.agent.id") or attributes.get("anthropic.agent.id")))
    assign(variables, "gen_ai.agent.name", to_str_or_none(attributes.get("gen_ai.agent.name") or attributes.get("anthropic.agent.name")))
    assign(variables, "gen_ai.agent.description", to_str_or_none(attributes.get("gen_ai.agent.description") or attributes.get("anthropic.agent.description")))
    assign(variables, "gen_ai.conversation.id", to_str_or_none(attributes.get("gen_ai.conversation.id")))
    if kind_val == "AGENT":
        assign(variables, "is_agent", True)
    if kind_val == "TOOL":
        assign(variables, "gen_ai.tool.name", to_str_or_none(attributes.get("gen_ai.tool.name")))
        assign(variables, "gen_ai.tool.call.id", to_str_or_none(attributes.get("gen_ai.tool.call.id")))
        assign(variables, "gen_ai.tool.type", to_str_or_none(attributes.get("gen_ai.tool.type")))

    # Legacy LLM fields
    system_text = _system_text(system_instructions)
    assign(variables, "llm_model", to_str_or_none(model or attributes.get("gen_ai.response.model")))
    assign(variables, "llm_system", system_text)
    assign(variables, "llm_tools", tool_definitions)
    assign(variables, "llm_invocation_parameters", invocation_params or None)

    if kind_val == "TOOL":
        # Tool spans: arguments in, result out (same as OpenAI Agents function spans)
        input_val = to_str_or_none(_parse_json(attributes.get("gen_ai.tool.call.arguments")))
        tool_result = attributes.get("gen_ai.tool.call.result")
        if tool_result is None:
            tool_result = attributes.get("anthropic.tool_result.content")
        output_val = to_str_or_none(_parse_json(tool_result))
    else:
        input_parts: List[str] = []
        if system_text:
            input_parts.append(f"System: {system_text}")
        flattened_input = flatten_messages(input_messages)
        if flattened_input:
            input_parts.append(flattened_input)
        input_val = "\n\n".join(input_parts) if input_parts else None
        output_val = flatten_messages(output_messages)
    assign(variables, "llm_input", input_val)
    assign(variables, "llm_output", output_val)

    # Resource, source, streaming, events, raw
    assign(variables, "otel_resource", json.dumps(resource_attrs, default=str))
    assign(variables, "from_source", from_source)
    if attributes.get("gen_ai.request.stream") or attributes.get("anthropic.request.stream"):
        assign(variables, "is_streaming", True)
    if span.get("events"):
        assign(variables, "events", json.dumps(span["events"], default=str))
    assign(variables, "raw", json.dumps(span, default=str))

    # cvs198 (collection level) is set by the exporter, which knows what it sends
    return reassign(variables, key_to_cvs, (starting_indices or CLAUDE_STARTING_INDICES).copy())
