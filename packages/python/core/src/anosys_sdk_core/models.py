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
    "server.address": "cvs14",
    "server.port": "cvn3",
    "error.type": "cvs10",
    "llm_model_name": "cvs16",
    "service.name": "cvs17",
    "attributes": "cvs18",
    
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
    "llm_input_messages": "gen_ai_input_messages",
    "llm_output_messages": "gen_ai_output_messages",
    
    # Decorator-specific fields
    "input": "llm_input",
    "output": "llm_output",
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
    "is_agent": "cvb1",
    "events": "otel_events",
    "user_context": "cvs5",
    "gen_ai.request.tool_choice": "cvs15",
}

# Validation maps per source based on Protobuf schemas
OTEL_AI_VALID_TYPES = {
    "timestamp": "timestamp",
    "user_timestamp": "double",
    "risk_score": "double",
    "is_anomaly": "boolean",
    "debug": "boolean",
    "otel_observed_timestamp": "timestamp",
    "otel_resource": "json",
    "otel_start_time": "timestamp",
    "otel_end_time": "timestamp",
    "otel_duration_ms": "double",
    "otel_attributes": "json",
    "otel_events": "json",
    "otel_links": "json",
    "otel_severity_number": "double",
    "otel_value": "double",
    "otel_labels": "json",
    "otel_histogram_bucket_counts": "json",
    "otel_histogram_bucket_bounds": "json",
    "otel_summary_count": "double",
    "otel_summary_sum": "double",
    "llm_tools": "json",
    "llm_token_count": "json",
    "llm_invocation_parameters": "json",
    "gen_ai_request_temperature": "double",
    "gen_ai_request_top_p": "double",
    "gen_ai_request_top_k": "double",
    "gen_ai_request_max_tokens": "double",
    "gen_ai_request_frequency_penalty": "double",
    "gen_ai_request_presence_penalty": "double",
    "gen_ai_request_seed": "double",
    "gen_ai_request_choice_count": "double",
    "gen_ai_usage_input_tokens": "double",
    "gen_ai_usage_output_tokens": "double",
    "gen_ai_usage_total_tokens": "double",
    "gen_ai_embeddings_dimension_count": "double",
    "gen_ai_request_stop_sequences": "json",
    "gen_ai_request_encoding_formats": "json",
    "gen_ai_response_finish_reasons": "json",
    "gen_ai_input_messages": "json",
    "gen_ai_output_messages": "json",
    "gen_ai_system_instructions": "json",
    "gen_ai_tool_definitions": "json",
}

CLAUDE_VALID_TYPES = {
    "timestamp": "timestamp",
    "user_timestamp": "double",
    "risk_score": "double",
    "is_anomaly": "boolean",
    "debug": "boolean",
    "input_tokens": "double",
    "output_tokens": "double",
    "total_tokens": "double",
    "cache_read": "double",
    "cache_creation": "double",
    "duration_ms": "double",
    "cost_estimate": "double",
    "incremental_input": "double",
    "incremental_output": "double",
    "incremental_total": "double",
    "incremental_cost": "double",
    "hook_count": "double",
    "max_retries": "double",
    "retry_attempt": "double",
    "retry_in_ms": "double",
    "log_index": "double",
    "has_thinking": "boolean",
    "is_api_error_message": "boolean",
    "is_meta": "boolean",
    "is_sidechain": "boolean",
    "is_snapshot_update": "boolean",
    "has_output": "boolean",
    "prevented_continuation": "boolean",
    "is_agent": "boolean",
}

# Legacy support - defaults to OTEL_AI
CORE_VALID_TYPES = OTEL_AI_VALID_TYPES



# Default starting indices for dynamic CVS variable allocation
DEFAULT_STARTING_INDICES = {
    "string": 100,
    "number": 3,
    "bool": 1,
}
