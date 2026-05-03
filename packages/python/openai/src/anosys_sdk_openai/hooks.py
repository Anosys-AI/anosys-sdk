"""
Span extraction hooks for AnoSys OpenAI SDK.

Provides functions to extract and transform OpenAI span information
into the format expected by the AnoSys API.
"""

import json
from datetime import datetime
from typing import Any, Dict, Optional

from anosys_sdk_core.util.json import to_str_or_none
from anosys_sdk_core.util.batching import assign, reassign
from anosys_sdk_openai.mapping import OPENAI_KEY_MAPPING, OPENAI_STARTING_INDICES


def _to_timestamp(dt_str: Optional[str]) -> Optional[int]:
    """Convert ISO datetime string to milliseconds timestamp."""
    if not dt_str:
        return None
    try:
        return int(datetime.fromisoformat(dt_str.replace('Z', '+00:00')).timestamp() * 1000)
    except (ValueError, AttributeError):
        return None


def set_nested(obj: Dict, path: str, value: Any) -> None:
    """Helper to set nested dictionary values from dotted paths."""
    parts = path.split(".")
    current = obj
    
    for i, part in enumerate(parts[:-1]):
        try:
            idx = int(part)
            if not isinstance(current, list):
                current_parent = current
                current = []
                if isinstance(current_parent, dict) and i > 0:
                    current_parent[parts[i - 1]] = current
            while len(current) <= idx:
                current.append({})
            current = current[idx]
        except ValueError:
            if part not in current or not isinstance(current[part], (dict, list)):
                current[part] = {}
            current = current[part]
    
    final_key = parts[-1]
    try:
        final_key = int(final_key)
        if not isinstance(current, list):
            current_parent = current
            current = []
            if isinstance(current_parent, dict):
                current_parent[parts[-2]] = current
        while len(current) <= final_key:
            current.append(None)
    except ValueError:
        pass
    
    # Try to parse JSON strings
    if isinstance(value, str) and value.strip().startswith(("{", "[")):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            pass
    
    if isinstance(final_key, int):
        current[final_key] = value
    else:
        current[final_key] = value


def deserialize_attributes(obj: Dict) -> Dict:
    """Deserialize flattened attributes into nested structure."""
    flat_attrs = obj.get("attributes", {})
    new_attrs = {}
    for key, value in flat_attrs.items():
        set_nested(new_attrs, key, value)
    obj["attributes"] = new_attrs
    return obj


def extract_span_info(span: Dict) -> Dict[str, Any]:
    """
    Extract and transform span information into AnoSys format.
    
    Includes OpenTelemetry semantic conventions for Gen AI.
    
    Args:
        span: Span dictionary from to_json()
        
    Returns:
        Transformed dictionary ready for AnoSys API
    """
    # Make a copy and deserialize nested attributes
    span = deserialize_attributes(span.copy())
    
    variables: Dict[str, Any] = {}
    key_to_cvs = OPENAI_KEY_MAPPING.copy()
    
    # Top-level metadata
    assign(variables, 'otel_record_type', 'AnoSys Trace')
    assign(variables, 'custom_mapping', json.dumps(key_to_cvs, indent=4))
    assign(variables, 'otel_observed_timestamp', datetime.utcnow().isoformat() + "Z")
    assign(variables, 'name', to_str_or_none(span.get('name')))
    assign(variables, 'trace_id', to_str_or_none(span.get('context', {}).get('trace_id')))
    assign(variables, 'span_id', to_str_or_none(span.get('context', {}).get('span_id')))
    assign(variables, 'trace_state', to_str_or_none(span.get('context', {}).get('trace_state')))
    assign(variables, 'parent_id', to_str_or_none(span.get('parent_id')))
    assign(variables, 'start_time', to_str_or_none(span.get('start_time')))
    assign(variables, 'cvn1', _to_timestamp(span.get('start_time')))
    assign(variables, 'end_time', to_str_or_none(span.get('end_time')))
    assign(variables, 'cvn2', _to_timestamp(span.get('end_time')))
    
    # Duration calculation
    start_ts = _to_timestamp(span.get('start_time'))
    end_ts = _to_timestamp(span.get('end_time'))
    if start_ts and end_ts:
        assign(variables, 'otel_duration_ms', end_ts - start_ts)
    
    # Status information
    status = span.get('status', {})
    if status:
        assign(variables, 'status', to_str_or_none(status))
        status_code = status.get('status_code')
        if status_code:
            status_map = {0: 'UNSET', 1: 'OK', 2: 'ERROR'}
            assign(variables, 'status_code', status_map.get(status_code, str(status_code)))
    
    # Attributes
    attributes = span.get('attributes', {})
    
    # Gen AI - System
    assign(variables, 'gen_ai.system', 'openai')
    assign(variables, 'gen_ai.provider.name', 'openai')
    
    # Operation name from span name
    span_name = span.get('name', '')
    if span_name:
        operation = span_name.split('.')[0] if '.' in span_name else span_name
        assign(variables, 'gen_ai.operation.name', operation)
    
    # Server address
    resource_attrs = span.get('resource', {}).get('attributes', {})
    server_addr = resource_attrs.get('server.address') or 'api.openai.com'
    server_port = resource_attrs.get('server.port') or 443
    assign(variables, 'server.address', server_addr)
    assign(variables, 'server.port', server_port)
    
    # Extract model information
    llm_attrs = attributes.get('llm', {})
    invocation_params = llm_attrs.get('invocation_parameters', {})
    
    if isinstance(invocation_params, str):
        try:
            invocation_params = json.loads(invocation_params)
        except json.JSONDecodeError:
            invocation_params = {}
    
    # Request configuration
    model_name = llm_attrs.get('model_name')
    if model_name:
        assign(variables, 'gen_ai.request.model', to_str_or_none(model_name))
    
    if isinstance(invocation_params, dict):
        temperature = invocation_params.get('temperature')
        max_tokens = invocation_params.get('max_tokens')
        top_p = invocation_params.get('top_p')
        top_k = invocation_params.get('top_k')
        frequency_penalty = invocation_params.get('frequency_penalty')
        presence_penalty = invocation_params.get('presence_penalty')
        stop_sequences = invocation_params.get('stop')
        seed = invocation_params.get('seed')
        n = invocation_params.get('n')
        
        if temperature is not None:
            assign(variables, 'gen_ai.request.temperature', temperature)
        if max_tokens is not None:
            assign(variables, 'gen_ai.request.max_tokens', max_tokens)
        if top_p is not None:
            assign(variables, 'gen_ai.request.top_p', top_p)
        if top_k is not None:
            assign(variables, 'gen_ai.request.top_k', top_k)
        if frequency_penalty is not None:
            assign(variables, 'gen_ai.request.frequency_penalty', frequency_penalty)
        if presence_penalty is not None:
            assign(variables, 'gen_ai.request.presence_penalty', presence_penalty)
        if stop_sequences is not None:
            assign(variables, 'gen_ai.request.stop_sequences', stop_sequences)
        if seed is not None:
            assign(variables, 'gen_ai.request.seed', seed)
        if n is not None:
            assign(variables, 'gen_ai.request.choice.count', n)
    
    # Extract output information
    output_attr = attributes.get('output', {})
    response_model = None
    response_id = None
    finish_reasons = []
    output_type = None
    output_value = {}
    
    if isinstance(output_attr, dict):
        output_value = output_attr.get('value') or {}
        if isinstance(output_value, str):
            try:
                output_value = json.loads(output_value)
            except json.JSONDecodeError:
                pass
        
        if isinstance(output_value, dict):
            response_id = output_value.get('id')
            response_model = output_value.get('model')
            object_type = output_value.get('object')
            
            if object_type:
                if 'chat' in object_type:
                    output_type = 'text'
                elif 'embedding' in object_type:
                    output_type = 'embedding'
                elif 'image' in object_type:
                    output_type = 'image'
            
            # JSON mode check
            if invocation_params.get('response_format', {}).get('type') == 'json_object':
                output_type = 'json'
            
            # Finish reasons
            choices = output_value.get('choices', [])
            if isinstance(choices, list):
                for choice in choices:
                    if isinstance(choice, dict):
                        finish_reason = choice.get('finish_reason')
                        if finish_reason:
                            finish_reasons.append(finish_reason)
    
    # Response & Usage
    if response_model:
        assign(variables, 'gen_ai.response.model', to_str_or_none(response_model))
    if response_id:
        assign(variables, 'gen_ai.response.id', to_str_or_none(response_id))
    if finish_reasons:
        assign(variables, 'gen_ai.response.finish_reasons', finish_reasons)
    if output_type:
        assign(variables, 'gen_ai.output.type', output_type)
    
    # Token usage
    token_count = llm_attrs.get('token_count', {})
    if isinstance(token_count, str):
        try:
            token_count = json.loads(token_count)
        except json.JSONDecodeError:
            token_count = {}
    
    if isinstance(token_count, dict):
        input_tokens = token_count.get('prompt_tokens') or token_count.get('input_tokens')
        output_tokens = token_count.get('completion_tokens') or token_count.get('output_tokens')
        total_tokens = token_count.get('total_tokens')
        
        if input_tokens is not None:
            assign(variables, 'gen_ai.usage.input_tokens', input_tokens)
        if output_tokens is not None:
            assign(variables, 'gen_ai.usage.output_tokens', output_tokens)
        if total_tokens is not None:
            assign(variables, 'gen_ai.usage.total_tokens', total_tokens)
        elif input_tokens is not None and output_tokens is not None:
            assign(variables, 'gen_ai.usage.total_tokens', input_tokens + output_tokens)
    
    # Input messages
    input_messages = None
    input_msg_attr = llm_attrs.get('input_messages', {})
    if isinstance(input_msg_attr, dict):
        input_messages = input_msg_attr.get('input_messages')
    if not input_messages and isinstance(invocation_params, dict):
        input_messages = invocation_params.get('messages')
    if input_messages:
        assign(variables, 'gen_ai.input.messages', to_str_or_none(input_messages))
    
    # Output messages
    output_messages = None
    output_msg_attr = llm_attrs.get('output_messages', {})
    if isinstance(output_msg_attr, dict):
        output_messages = output_msg_attr.get('output_messages')
    if not output_messages and isinstance(output_value, dict):
        choices = output_value.get('choices', [])
        if choices:
            messages = [choice.get('message') for choice in choices if choice.get('message')]
            if messages:
                output_messages = messages
    if output_messages:
        assign(variables, 'gen_ai.output.messages', to_str_or_none(output_messages))
    
    # System instructions
    system_content = llm_attrs.get('system')
    if not system_content and input_messages:
        if isinstance(input_messages, list):
            for msg in input_messages:
                if isinstance(msg, dict) and msg.get('role') == 'system':
                    system_content = msg.get('content')
                    break
        elif isinstance(input_messages, str):
            try:
                parsed_messages = json.loads(input_messages)
                if isinstance(parsed_messages, list):
                    for msg in parsed_messages:
                        if isinstance(msg, dict) and msg.get('role') == 'system':
                            system_content = msg.get('content')
                            break
            except json.JSONDecodeError:
                pass
    if system_content:
        assign(variables, 'gen_ai.system_instructions', to_str_or_none(system_content))
    
    # Tools
    tools = llm_attrs.get('tools')
    if not tools and isinstance(invocation_params, dict):
        tools = invocation_params.get('tools')
    if tools:
        assign(variables, 'gen_ai.tool.definitions', to_str_or_none(tools))
    
    # Legacy LLM fields
    assign(variables, 'llm_tools', to_str_or_none(llm_attrs.get('tools')))
    assign(variables, 'llm_token_count', to_str_or_none(llm_attrs.get('token_count')))
    assign(variables, 'llm_output_messages', to_str_or_none(
        llm_attrs.get('output_messages', {}).get('output_messages')))
    assign(variables, 'llm_input_messages', to_str_or_none(
        llm_attrs.get('input_messages', {}).get('input_messages')))
    assign(variables, 'llm_model', to_str_or_none(model_name))
    assign(variables, 'llm_invocation_parameters', to_str_or_none(invocation_params))
    assign(variables, 'llm_system', to_str_or_none(llm_attrs.get('system')))
    assign(variables, 'llm_input', to_str_or_none(attributes.get('input', {}).get('value')))
    llm_output_val = output_attr.get('value') if isinstance(output_attr, dict) else output_attr
    assign(variables, 'llm_output', to_str_or_none(llm_output_val))
    assign(variables, 'kind', to_str_or_none(attributes.get('fi', {}).get('span', {}).get('kind')))
    
    # Resource
    assign(variables, 'otel_resource', json.dumps(span.get('resource', {}).get('attributes'), default=str))
    assign(variables, 'from_source', "openAI_Python_Telemetry")
    
    # Response ID
    assign(variables, 'resp_id', to_str_or_none(response_id))
    
    # Streaming
    is_streaming = invocation_params.get('stream', False) if isinstance(invocation_params, dict) else False
    if is_streaming:
        assign(variables, 'is_streaming', True)
    
    # Raw data
    assign(variables, "raw", json.dumps(span, default=str))
    
    return reassign(variables, key_to_cvs, OPENAI_STARTING_INDICES.copy())
