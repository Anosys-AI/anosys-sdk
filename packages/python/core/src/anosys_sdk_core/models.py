"""
Data models and mappings for AnoSys SDK.

Defines the base CVS variable mapping schema used across all AnoSys integrations.
"""

from typing import Dict

# Base key-to-CVS variable mapping
# This is the core mapping shared by all packages
BASE_KEY_MAPPING: Dict[str, str] = {
    # Schema and metadata
    "custom_mapping": "otel_schema_url",
    "otel_observed_timestamp": "otel_observed_timestamp",
    "otel_record_type": "otel_record_type",
    
    # Timing
    "cvn1": "cvn1",  # Start timestamp (numeric)
    "cvn2": "cvn2",  # End timestamp (numeric)
    "otel_duration_ms": "otel_duration_ms",
    
    # Trace/Span identifiers
    "name": "otel_name",
    "trace_id": "otel_trace_id",
    "span_id": "otel_span_id",
    "trace_state": "otel_trace_flags",
    "parent_id": "otel_parent_span_id",
    "start_time": "otel_start_time",
    "end_time": "otel_end_time",
    "kind": "otel_kind",
    
    # Status
    "status": "otel_status",
    "status_code": "otel_status_code",
    "resp_id": "otel_status_message",
    
    # Resources
    "otel_resource": "otel_resource",
    
    # Gen AI - General & System
    "gen_ai.system": "gen_ai_system",
    "gen_ai.provider.name": "gen_ai_provider_name",
    "gen_ai.operation.name": "gen_ai_operation_name",
    "server.address": "server_address",
    "server.port": "server_port",
    "error.type": "error_type",
    
    # Gen AI - Request Configuration
    "gen_ai.request.model": "gen_ai_request_model",
    "gen_ai.request.temperature": "gen_ai_request_temperature",
    "gen_ai.request.top_p": "gen_ai_request_top_p",
    "gen_ai.request.top_k": "gen_ai_request_top_k",
    "gen_ai.request.max_tokens": "gen_ai_request_max_tokens",
    "gen_ai.request.frequency_penalty": "gen_ai_request_frequency_penalty",
    "gen_ai.request.presence_penalty": "gen_ai_request_presence_penalty",
    "gen_ai.request.stop_sequences": "gen_ai_request_stop_sequences",
    "gen_ai.request.seed": "gen_ai_request_seed",
    "gen_ai.request.choice.count": "gen_ai_request_choice_count",
    "gen_ai.request.encoding_formats": "gen_ai_request_encoding_formats",
    
    # Gen AI - Response & Usage
    "gen_ai.response.model": "gen_ai_response_model",
    "gen_ai.response.id": "gen_ai_response_id",
    "gen_ai.response.finish_reasons": "gen_ai_response_finish_reasons",
    "gen_ai.usage.input_tokens": "gen_ai_usage_input_tokens",
    "gen_ai.usage.output_tokens": "gen_ai_usage_output_tokens",
    "gen_ai.usage.total_tokens": "gen_ai_usage_total_tokens",
    "gen_ai.output.type": "gen_ai_output_type",
    
    # Gen AI - Content & Messages
    "gen_ai.input.messages": "gen_ai_input_messages",
    "gen_ai.output.messages": "gen_ai_output_messages",
    "gen_ai.system_instructions": "gen_ai_system_instructions",
    "gen_ai.tool.definitions": "gen_ai_tool_definitions",
    
    # Gen AI - Agents & Frameworks
    "gen_ai.agent.id": "gen_ai_agent_id",
    "gen_ai.agent.name": "gen_ai_agent_name",
    "gen_ai.agent.description": "gen_ai_agent_description",
    "gen_ai.conversation.id": "gen_ai_conversation_id",
    "gen_ai.data_source.id": "gen_ai_data_source_id",
    
    # Gen AI - Embeddings
    "gen_ai.embeddings.dimension.count": "gen_ai_embeddings_dimension_count",
    
    # Legacy LLM fields (backward compatibility)
    "llm_tools": "llm_tools",
    "llm_system": "llm_system",
    "llm_input": "llm_input",
    "llm_output": "llm_output",
    "llm_model": "llm_model",
    "llm_invocation_parameters": "llm_invocation_parameters",
    "llm_token_count": "llm_token_count",
    "llm_input_messages": "cvs1",
    "llm_output_messages": "cvs2",
    
    # Decorator-specific fields
    "input": "cvs1",
    "output": "cvs2",
    "error": "cvs3",
    "caller": "cvs4",
    "error_type": "cvs10",
    "error_message": "cvs11",
    "error_stack": "cvs12",
    
    # Source tracking
    "raw": "cvs199",
    "from_source": "cvs200",
    "source": "cvs200",
    "is_streaming": "cvb2",
}

# Default starting indices for dynamic CVS variable allocation
DEFAULT_STARTING_INDICES = {
    "string": 100,
    "number": 3,
    "bool": 1,
}
