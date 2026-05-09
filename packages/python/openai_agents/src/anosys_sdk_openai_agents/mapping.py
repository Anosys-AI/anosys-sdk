"""
Mapping and transformation utilities for OpenAI Agents spans.

Provides functions to transform agent spans into the format expected by AnoSys.
"""

import json
from datetime import datetime
from typing import Any, Dict, Optional

from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan

from anosys_sdk_core.models import BASE_KEY_MAPPING, DEFAULT_STARTING_INDICES
from anosys_sdk_core.util.json import to_str_or_none
from anosys_sdk_core.util.batching import assign, reassign

# Agents-specific key mapping
AGENTS_KEY_MAPPING = {
    **BASE_KEY_MAPPING,
    # Metadata and Status
    "cvs60": "cvs60",  # Object type (trace/trace.span)
    "cvs61": "cvs61",  # Source (span_start/span_end)
    "cvs62": "cvs62",  # Handoffs
    "cvs63": "cvs63",  # Tools
    "cvs64": "cvs64",  # Output type
    "cvs67": "cvs67",  # MCP data
    "cvs72": "cvs72",  # Data
    "cvs73": "cvs73",  # Format
    "cvs74": "cvs74",  # First content at
    "cvs75": "cvs75",  # Server
    "cvs76": "cvs76",  # Result
    "cvs77": "cvs77",  # Response ID
    "cvs78": "cvs78",  # From agent
    "cvs79": "cvs79",  # To agent
}

AGENTS_STARTING_INDICES = DEFAULT_STARTING_INDICES.copy()


def _to_timestamp(dt_str) -> Optional[int]:
    """Convert ISO datetime string to milliseconds timestamp."""
    if not dt_str:
        return None
    try:
        return int(datetime.fromisoformat(str(dt_str)).timestamp() * 1000)
    except ValueError:
        return None


def _to_int_safe(val: Any) -> Optional[int]:
    """Safely convert a value to an integer, handling nested objects."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    if isinstance(val, str):
        try:
            return int(float(val))
        except (ValueError, TypeError):
            pass
    if isinstance(val, dict):
        # Look for common count keys in the details object
        for key in ["total", "count", "tokens", "value", "cached_tokens", "reasoning_tokens"]:
            if key in val:
                result = _to_int_safe(val[key])
                if result is not None:
                    return result
        # Fallback: if it's an object with only detail keys, it might be 0 or a sum
        return 0
    return None


def span2json(span: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform an agent span payload into AnoSys format.
    
    Args:
        span: Span dictionary with data and user_context
        
    Returns:
        Transformed dictionary for AnoSys API
    """
    data = span.get("data", {})
    span_data = data.get("span_data", {})
    source = data.get("source")
    timestamp = span.get("timestamp")
    user_context = json.dumps(span.get("user_context", {}))
    
    def clean_dict(d):
        return {k: v for k, v in d.items() if v is not None}
    
    # Field documentation mapping
    mapping = {
        "otel_record_type": "record type (AnoSys Agentic Trace)",
        "otel_schema_url": "schema URL (custom_mapping)",
        "otel_observed_timestamp": "creation timestamp",
        "g1": "creation timestamp (numeric)",
        "otel_span_id": "span id",
        "otel_trace_id": "trace id",
        "otel_parent_span_id": "parent span id",
        "otel_start_time": "span start time",
        "cvn1": "start time (numeric)",
        "otel_end_time": "span end time",
        "cvn2": "end time (numeric)",
        "otel_exception_message": "error message",
        "cvs3": "user context",
        "cvs60": "object type",
        "cvs61": "source",
        "otel_name": "span name",
        "otel_duration_ms": "duration in ms",
    }
    
    base = {
        "otel_record_type": "AnoSys Agentic Trace",
        "otel_schema_url": json.dumps(mapping, default=str),
        "otel_observed_timestamp": to_str_or_none(timestamp),
        "g1": _to_timestamp(timestamp),
        
        "otel_span_id": to_str_or_none(data.get("id")),
        "otel_trace_id": to_str_or_none(data.get("trace_id")) or to_str_or_none(data.get("id")),
        "otel_parent_span_id": to_str_or_none(data.get("parent_id")),
        "otel_start_time": to_str_or_none(data.get("started_at")),
        "cvn1": _to_timestamp(data.get("started_at")),
        "otel_end_time": to_str_or_none(data.get("ended_at")),
        "cvn2": _to_timestamp(data.get("ended_at")),
        "otel_exception_message": to_str_or_none(data.get("error")),
        
        "cvs3": to_str_or_none(user_context),
        "cvs60": to_str_or_none(data.get("object")),
        "cvs61": to_str_or_none(source),
    }
    
    # Calculate duration
    start_ts = _to_timestamp(data.get("started_at"))
    end_ts = _to_timestamp(data.get("ended_at"))
    if start_ts is not None and end_ts is not None:
        base["otel_duration_ms"] = end_ts - start_ts
    else:
        base["otel_duration_ms"] = None
    
    type_ = span_data.get("type")
    
    def _extract_id_from_config(config) -> Dict[str, Any]:
        if isinstance(config, dict) and "id" in config:
            return {"cvs77": to_str_or_none(config.get("id"))}
        if isinstance(config, str):
            try:
                parsed = json.loads(config)
                if isinstance(parsed, dict) and "id" in parsed:
                    return {"cvs77": to_str_or_none(parsed.get("id"))}
            except Exception:
                pass
        return {}

    # Type-specific field handlers
    extended = {
        "agent": lambda: {
            "otel_name": to_str_or_none(span_data.get("name")),
            "cvs62": to_str_or_none(", ".join(span_data.get("handoffs") or [])),
            "llm_tools": to_str_or_none(", ".join(span_data.get("tools") or [])),
            "cvs64": to_str_or_none(span_data.get("output_type")),
        },
        "function": lambda: {
            "otel_name": to_str_or_none(span_data.get("name")),
            "llm_input": to_str_or_none(span_data.get("input")),
            "llm_output": to_str_or_none(span_data.get("output")),
            "cvs67": to_str_or_none(span_data.get("mcp_data")),
        },
        "mcp_tools": lambda: {
            "otel_name": to_str_or_none(span_data.get("name")),
            "llm_input": to_str_or_none(span_data.get("input")),
            "llm_output": to_str_or_none(span_data.get("output")),
            "cvs67": to_str_or_none(span_data.get("mcp_data")),
        },
        "guardrail": lambda: {
            "otel_name": to_str_or_none(span_data.get("name")),
            "cvs68": to_str_or_none(span_data.get("triggered")),
        },
        "generation": lambda: {
            "llm_input": to_str_or_none(span_data.get("input")),
            "llm_output": to_str_or_none(span_data.get("output")),
            "cvs69": to_str_or_none(span_data.get("model")),
            "llm_invocation_parameters": to_str_or_none(span_data.get("model_config")),
            "llm_token_count": to_str_or_none(span_data.get("usage")),
            **_extract_id_from_config(span_data.get("model_config"))
        },
        "custom": lambda: {
            "otel_name": to_str_or_none(span_data.get("name")),
            "cvs72": to_str_or_none(span_data.get("data")),
        },
        "transcription": lambda: {
            "cvs72": to_str_or_none(span_data.get("input", {}).get("data")),
            "cvs73": to_str_or_none(span_data.get("input", {}).get("format")),
            "cvs66": to_str_or_none(span_data.get("output")),
            "cvs69": to_str_or_none(span_data.get("model")),
            "cvs70": to_str_or_none(span_data.get("model_config")),
            **_extract_id_from_config(span_data.get("model_config"))
        },
        "speech": lambda: {
            "llm_input": to_str_or_none(span_data.get("input")),
            "cvs72": to_str_or_none(span_data.get("output", {}).get("data")),
            "cvs73": to_str_or_none(span_data.get("output", {}).get("format")),
            "cvs69": to_str_or_none(span_data.get("model")),
            "llm_invocation_parameters": to_str_or_none(span_data.get("model_config")),
            "cvs74": to_str_or_none(span_data.get("first_content_at")),
            **_extract_id_from_config(span_data.get("model_config"))
        },
        "speechgroup": lambda: {
            "cvs65": to_str_or_none(span_data.get("input")),
        },
        "MCPListTools": lambda: {
            "cvs75": to_str_or_none(span_data.get("server")),
            "cvs76": to_str_or_none(span_data.get("result")),
        },
        "response": lambda: {
            "cvs77": to_str_or_none(span_data.get("response_id")),
        },
        "handoff": lambda: {
            "cvs78": to_str_or_none(span_data.get("from_agent")),
            "cvs79": to_str_or_none(span_data.get("to_agent")),
        },
    }
    
    result = {
        **base,
        "otel_kind": to_str_or_none(type_),
        "cvb1": True,
        "cvs199": json.dumps(span, default=str),
        "cvs200": "openAI_Agents_Traces"
    }
    
    if type_ in extended:
        result.update(extended[type_]())
    
    return clean_dict(result)


def set_nested(obj: Dict, path: str, value: Any) -> None:
    """Set nested dictionary value from dotted path."""
    parts = path.split(".")
    current = obj
    
    for i, part in enumerate(parts[:-1]):
        try:
            idx = int(part)
            if not isinstance(current, list):
                current = []
            while len(current) <= idx:
                current.append({})
            current = current[idx]
        except ValueError:
            if part not in current or not isinstance(current[part], (dict, list)):
                current[part] = {}
            current = current[part]
    
    final_key = parts[-1]
    if isinstance(value, str) and value.strip().startswith(("{", "[")):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            pass
    
    current[final_key] = value


def deserialize_attributes(attributes: Dict) -> Dict:
    """Deserialize flattened attributes into nested structure."""
    new_attrs = {}
    for key, value in attributes.items():
        set_nested(new_attrs, key, value)

    return new_attrs


def span_to_dict(span: ReadableSpan) -> Dict[str, Any]:
    """
    Convert a ReadableSpan to a clean dictionary for raw dump (cvs199).
    
    Extracts the full span structure including events, links,
    and instrumentation scope.
    
    Args:
        span: OpenTelemetry ReadableSpan object
        
    Returns:
        Dictionary representation of the span
    """
    return {
        "name": span.name,
        "context": {
            "trace_id": format(span.context.trace_id, "032x"),
            "span_id": format(span.context.span_id, "016x"),
            "trace_flags": int(span.context.trace_flags),
        },
        "parent_id": (
            format(span.parent.span_id, "016x")
            if span.parent else None
        ),
        "kind": span.kind.name,
        "start_time_unix_nano": span.start_time,
        "end_time_unix_nano": span.end_time,
        "status": {
            "status_code": span.status.status_code.name,
            "description": span.status.description,
        },
        "attributes_json": deserialize_attributes(dict(span.attributes)) if span.attributes else {},
        "events": [
            {
                "name": event.name,
                "timestamp": event.timestamp,
                "attributes": dict(event.attributes),
            }
            for event in span.events
        ],
        "links": [
            {
                "context": {
                    "trace_id": format(link.context.trace_id, "032x"),
                    "span_id": format(link.context.span_id, "016x"),
                },
                "attributes": dict(link.attributes),
            }
            for link in span.links
        ],
        "resource": dict(span.resource.attributes),
        "instrumentation_scope": {
            "name": span.instrumentation_scope.name,
            "version": span.instrumentation_scope.version,
        },
    }


def extract_otel_span_info(span: ReadableSpan) -> Dict[str, Any]:
    """
    Extract span info directly from OpenTelemetry ReadableSpan.
    
    Includes all Gen AI semantic conventions, legacy LLM fields,
    and raw span dump for cvs199.
    
    Args:
        span: OpenTelemetry ReadableSpan object
        
    Returns:
        Dictionary formatted for AnoSys API
    """
    variables = {}
    key_to_cvs = AGENTS_KEY_MAPPING.copy()
    
    # Timestamps (OTel uses nanoseconds)
    start_ts_ms = span.start_time // 1_000_000 if span.start_time else None
    end_ts_ms = span.end_time // 1_000_000 if span.end_time else None
    
    # Top-level metadata
    assign(variables, 'otel_record_type', 'AnoSys Trace')
    assign(variables, 'custom_mapping', json.dumps(key_to_cvs, indent=4))
    
    # IDs
    trace_id_hex = trace.format_trace_id(span.context.trace_id) if span.context.trace_id else None
    span_id_hex = trace.format_span_id(span.context.span_id) if span.context.span_id else None
    parent_id_hex = trace.format_span_id(span.parent.span_id) if span.parent else None
    
    assign(variables, 'otel_observed_timestamp', datetime.utcnow().isoformat() + "Z")
    assign(variables, 'name', span.name)
    assign(variables, 'trace_id', trace_id_hex)
    assign(variables, 'span_id', span_id_hex)
    assign(variables, 'trace_state', span.context.trace_state.to_header() if span.context.trace_state else None)
    assign(variables, 'parent_id', parent_id_hex)
    
    # Timestamps
    if start_ts_ms:
        variables['start_time'] = datetime.utcfromtimestamp(start_ts_ms / 1000.0).isoformat() + "Z"
    else:
        variables['start_time'] = None
    assign(variables, 'cvn1', start_ts_ms)
    
    if end_ts_ms:
        variables['end_time'] = datetime.utcfromtimestamp(end_ts_ms / 1000.0).isoformat() + "Z"
    else:
        variables['end_time'] = None
    assign(variables, 'cvn2', end_ts_ms)
    
    # Duration
    if start_ts_ms is not None and end_ts_ms is not None:
        assign(variables, 'otel_duration_ms', end_ts_ms - start_ts_ms)
    else:
        assign(variables, 'otel_duration_ms', None)
    
    # Deserialize flattened OTel attributes into nested structure
    attributes_json = deserialize_attributes(dict(span.attributes) if span.attributes else {})
    
    # --- Legacy / Backward Compatibility & Unified Extraction ---
    # Model
    model = (
        attributes_json.get('gen_ai', {}).get('request', {}).get('model') or 
        attributes_json.get('llm', {}).get('model_name')
    )
    assign(variables, 'llm_model', to_str_or_none(model))

    # Input / Output Values
    input_val = (
        attributes_json.get('input', {}).get('value') or 
        attributes_json.get('gen_ai', {}).get('input', {}).get('messages') or
        attributes_json.get('llm', {}).get('input_messages', {}).get('input_messages')
    )
    output_val = (
        attributes_json.get('output', {}).get('value') or 
        attributes_json.get('gen_ai', {}).get('output', {}).get('messages') or
        attributes_json.get('llm', {}).get('output_messages', {}).get('output_messages')
    )
    assign(variables, 'llm_input', to_str_or_none(input_val))
    assign(variables, 'llm_output', to_str_or_none(output_val))

    # Tokens
    tokens = (
        attributes_json.get('gen_ai', {}).get('usage') or 
        attributes_json.get('llm', {}).get('token_count')
    )
    # llm_token_count is 'json' type in schema, so we send the whole dict
    assign(variables, 'llm_token_count', tokens)

    # Parameters & System
    params = (
        attributes_json.get('gen_ai', {}).get('request', {}).get('parameters') or 
        attributes_json.get('llm', {}).get('invocation_parameters')
    )
    assign(variables, 'llm_invocation_parameters', to_str_or_none(params))
    
    if isinstance(params, dict) and 'id' in params:
        assign(variables, 'cvs77', to_str_or_none(params.get('id')))
    elif isinstance(params, str):
        try:
            parsed_params = json.loads(params)
            if isinstance(parsed_params, dict) and 'id' in parsed_params:
                assign(variables, 'cvs77', to_str_or_none(parsed_params.get('id')))
        except Exception:
            pass
    
    system = (
        attributes_json.get('gen_ai', {}).get('system_instructions') or 
        attributes_json.get('llm', {}).get('system')
    )
    assign(variables, 'llm_system', to_str_or_none(system))
    
    # Kind
    assign(variables, 'kind', str(span.kind).replace('SpanKind.', '').upper())
    
    # Resource
    assign(variables, 'otel_resource', json.dumps(dict(span.resource.attributes), default=str))
    assign(variables, 'from_source', "openAI_Agents_Telemetry")
    
    # --- Gen AI Semantic Conventions ---
    
    # General & System
    assign(variables, 'gen_ai.system', to_str_or_none(
        attributes_json.get('gen_ai', {}).get('system') or "openai"))
    assign(variables, 'gen_ai.provider.name', to_str_or_none(
        attributes_json.get('gen_ai', {}).get('provider', {}).get('name')))
    assign(variables, 'gen_ai.operation.name', to_str_or_none(
        attributes_json.get('gen_ai', {}).get('operation', {}).get('name')))
    assign(variables, 'server.address', to_str_or_none(
        attributes_json.get('server', {}).get('address')))
    assign(variables, 'server.port', attributes_json.get('server', {}).get('port'))
    assign(variables, 'error.type', to_str_or_none(
        attributes_json.get('error', {}).get('type')))
    
    # Request Configuration
    assign(variables, 'gen_ai.request.model', to_str_or_none(
        attributes_json.get('gen_ai', {}).get('request', {}).get('model') or
        attributes_json.get('llm', {}).get('model_name')))
    assign(variables, 'gen_ai.request.temperature',
        attributes_json.get('gen_ai', {}).get('request', {}).get('temperature'))
    assign(variables, 'gen_ai.request.top_p',
        attributes_json.get('gen_ai', {}).get('request', {}).get('top_p'))
    assign(variables, 'gen_ai.request.top_k',
        attributes_json.get('gen_ai', {}).get('request', {}).get('top_k'))
    assign(variables, 'gen_ai.request.max_tokens',
        attributes_json.get('gen_ai', {}).get('request', {}).get('max_tokens'))
    assign(variables, 'gen_ai.request.frequency_penalty',
        attributes_json.get('gen_ai', {}).get('request', {}).get('frequency_penalty'))
    assign(variables, 'gen_ai.request.presence_penalty',
        attributes_json.get('gen_ai', {}).get('request', {}).get('presence_penalty'))
    assign(variables, 'gen_ai.request.stop_sequences', to_str_or_none(
        attributes_json.get('gen_ai', {}).get('request', {}).get('stop_sequences')))
    assign(variables, 'gen_ai.request.seed',
        attributes_json.get('gen_ai', {}).get('request', {}).get('seed'))
    assign(variables, 'gen_ai.request.choice.count',
        attributes_json.get('gen_ai', {}).get('request', {}).get('choice', {}).get('count'))
    assign(variables, 'gen_ai.request.encoding_formats', to_str_or_none(
        attributes_json.get('gen_ai', {}).get('request', {}).get('encoding_formats')))
    
    # Response & Usage
    assign(variables, 'gen_ai.response.model', to_str_or_none(
        attributes_json.get('gen_ai', {}).get('response', {}).get('model')))
    assign(variables, 'gen_ai.response.id', to_str_or_none(
        attributes_json.get('gen_ai', {}).get('response', {}).get('id')))
    assign(variables, 'gen_ai.response.finish_reasons', to_str_or_none(
        attributes_json.get('gen_ai', {}).get('response', {}).get('finish_reasons')))
    
    # Ensure tokens are numbers
    assign(variables, 'gen_ai.usage.input_tokens', _to_int_safe(
        attributes_json.get('gen_ai', {}).get('usage', {}).get('input_tokens')))
    assign(variables, 'gen_ai.usage.output_tokens', _to_int_safe(
        attributes_json.get('gen_ai', {}).get('usage', {}).get('output_tokens')))
    assign(variables, 'gen_ai.usage.total_tokens', _to_int_safe(
        attributes_json.get('gen_ai', {}).get('usage', {}).get('total_tokens')))
    
    assign(variables, 'gen_ai.output.type', to_str_or_none(
        attributes_json.get('gen_ai', {}).get('output', {}).get('type')))
    
    # Content & Messages
    assign(variables, 'gen_ai.input.messages', to_str_or_none(
        attributes_json.get('gen_ai', {}).get('input', {}).get('messages')))
    assign(variables, 'gen_ai.output.messages', to_str_or_none(
        attributes_json.get('gen_ai', {}).get('output', {}).get('messages')))
    assign(variables, 'gen_ai.system_instructions', to_str_or_none(
        attributes_json.get('gen_ai', {}).get('system_instructions')))
    assign(variables, 'gen_ai.tool.definitions', to_str_or_none(
        attributes_json.get('gen_ai', {}).get('tool', {}).get('definitions')))
    
    # Agents & Frameworks
    assign(variables, 'gen_ai.agent.id', to_str_or_none(
        attributes_json.get('gen_ai', {}).get('agent', {}).get('id')))
    assign(variables, 'gen_ai.agent.name', to_str_or_none(
        attributes_json.get('gen_ai', {}).get('agent', {}).get('name')))
    assign(variables, 'gen_ai.agent.description', to_str_or_none(
        attributes_json.get('gen_ai', {}).get('agent', {}).get('description')))
    assign(variables, 'gen_ai.conversation.id', to_str_or_none(
        attributes_json.get('gen_ai', {}).get('conversation', {}).get('id')))
    assign(variables, 'gen_ai.data_source.id', to_str_or_none(
        attributes_json.get('gen_ai', {}).get('data_source', {}).get('id')))
    
    # Embeddings
    assign(variables, 'gen_ai.embeddings.dimension.count',
        attributes_json.get('gen_ai', {}).get('embeddings', {}).get('dimension', {}).get('count'))
    
    # Response ID extraction for linking with agent traces
    response_id = None
    output_value_val = attributes_json.get('output', {}).get('value')
    if not output_value_val:
        output_value_val = attributes_json.get('raw', {}).get('output')
    
    if isinstance(output_value_val, dict):
        response_id = output_value_val.get('id')
    elif isinstance(output_value_val, list) and output_value_val:
        first_item = output_value_val[0]
        if isinstance(first_item, dict):
            response_id = first_item.get('id')
    
    assign(variables, 'resp_id', to_str_or_none(response_id))
    
    # Raw attributes dump (cvs199)
    variables['raw'] = json.dumps(attributes_json, default=str)
    
    return reassign(variables, key_to_cvs, AGENTS_STARTING_INDICES.copy())
