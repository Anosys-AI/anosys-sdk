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
    # Agents-specific fields
    "g1": "g1",  # Creation timestamp numeric
    "cvs3": "cvs3",  # User context
    "cvs60": "cvs60",  # Object type (trace/trace.span)
    "cvs61": "cvs61",  # Source (span_start/span_end)
    "cvs62": "cvs62",  # Handoffs
    "cvs63": "cvs63",  # Tools
    "cvs64": "cvs64",  # Output type
    "cvs65": "cvs65",  # Input
    "cvs66": "cvs66",  # Output
    "cvs67": "cvs67",  # MCP data
    "cvs68": "cvs68",  # Triggered
    "cvs69": "cvs69",  # Model
    "cvs70": "cvs70",  # Model config
    "cvs71": "cvs71",  # Usage
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
    
    # Type-specific field handlers
    extended = {
        "agent": lambda: {
            "otel_name": to_str_or_none(span_data.get("name")),
            "cvs62": to_str_or_none(", ".join(span_data.get("handoffs") or [])),
            "cvs63": to_str_or_none(", ".join(span_data.get("tools") or [])),
            "cvs64": to_str_or_none(span_data.get("output_type")),
        },
        "function": lambda: {
            "otel_name": to_str_or_none(span_data.get("name")),
            "cvs65": to_str_or_none(span_data.get("input")),
            "cvs66": to_str_or_none(span_data.get("output")),
            "cvs67": to_str_or_none(span_data.get("mcp_data")),
        },
        "mcp_tools": lambda: {
            "otel_name": to_str_or_none(span_data.get("name")),
            "cvs65": to_str_or_none(span_data.get("input")),
            "cvs66": to_str_or_none(span_data.get("output")),
            "cvs67": to_str_or_none(span_data.get("mcp_data")),
        },
        "guardrail": lambda: {
            "otel_name": to_str_or_none(span_data.get("name")),
            "cvs68": to_str_or_none(span_data.get("triggered")),
        },
        "generation": lambda: {
            "cvs65": to_str_or_none(span_data.get("input")),
            "cvs66": to_str_or_none(span_data.get("output")),
            "cvs69": to_str_or_none(span_data.get("model")),
            "cvs70": to_str_or_none(span_data.get("model_config")),
            "cvs71": to_str_or_none(span_data.get("usage")),
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
        },
        "speech": lambda: {
            "cvs65": to_str_or_none(span_data.get("input")),
            "cvs72": to_str_or_none(span_data.get("output", {}).get("data")),
            "cvs73": to_str_or_none(span_data.get("output", {}).get("format")),
            "cvs69": to_str_or_none(span_data.get("model")),
            "cvs70": to_str_or_none(span_data.get("model_config")),
            "cvs74": to_str_or_none(span_data.get("first_content_at")),
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


def extract_otel_span_info(span: ReadableSpan) -> Dict[str, Any]:
    """
    Extract span info directly from OpenTelemetry ReadableSpan.
    
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
    assign(variables, 'cvn1', start_ts_ms)
    
    if end_ts_ms:
        variables['end_time'] = datetime.utcfromtimestamp(end_ts_ms / 1000.0).isoformat() + "Z"
    assign(variables, 'cvn2', end_ts_ms)
    
    if start_ts_ms and end_ts_ms:
        assign(variables, 'otel_duration_ms', end_ts_ms - start_ts_ms)
    
    # Attributes
    attributes_json = deserialize_attributes(dict(span.attributes) if span.attributes else {})
    
    # Gen AI fields
    assign(variables, 'gen_ai.system', to_str_or_none(attributes_json.get('gen_ai', {}).get('system') or "openai"))
    assign(variables, 'gen_ai.request.model', to_str_or_none(
        attributes_json.get('gen_ai', {}).get('request', {}).get('model') or 
        attributes_json.get('llm', {}).get('model_name')
    ))
    
    # Kind and resource
    assign(variables, 'kind', str(span.kind).replace('SpanKind.', '').upper())
    assign(variables, 'otel_resource', json.dumps(dict(span.resource.attributes), default=str))
    assign(variables, 'from_source', "openAI_Agents_Telemetry")
    
    return reassign(variables, key_to_cvs, AGENTS_STARTING_INDICES.copy())
