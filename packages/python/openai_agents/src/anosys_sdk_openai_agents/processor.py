"""
OpenAI Agents TracingProcessor for AnoSys SDK.

Provides the AnosysOpenAIAgentsLogger class that implements the TracingProcessor
interface to capture agent traces and send them to AnoSys.
"""

import json
import threading
import logging
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from traceai_openai_agents import OpenAIAgentsInstrumentor, TraceConfig

from agents import TracingProcessor

from anosys_sdk_core.config import resolve_api_key
from anosys_sdk_core.decorators import setup_api
from anosys_sdk_core.context import clean_contextvars
from anosys_sdk_core.capture import accepts_span, current_app_level, prepare_app_record, resolve_app_level
from anosys_sdk_core.privacy import FULL, OFF
from anosys_sdk_core.transport import send_app_record
from anosys_sdk_openai_agents.mapping import span2json, extract_otel_span_info
from anosys_sdk_openai_agents.utils import safe_serialize, clean_nulls

# Set up logging
logger = logging.getLogger(__name__)

# Module-level state
_lock = threading.Lock()
_tracing_initialized = False
_log_api_url = ""  # set by setup_tracing; empty = nothing is sent
_capture_level = None  # set by AnosysOpenAIAgentsLogger; until then the shared level applies (anosys_sdk_core.capture)

# Per-direction capture switches (set by AnosysOpenAIAgentsLogger) and the
# columns each one controls. Raw spans and attribute blobs repeat everything,
# so they go whenever any direction is switched off.
_capture_flags = {"inputs": True, "outputs": True, "parameters": True}
_pii = {"enabled": False}  # pii_redaction, applied on both the OTel and the processor path
INPUT_COLUMNS = ("llm_input", "gen_ai_input_messages", "gen_ai_system_instructions", "llm_system", "cvs65", "cvs71")
OUTPUT_COLUMNS = ("llm_output", "gen_ai_output_messages", "cvs66", "cvs67", "cvs72", "cvs76")
PARAMETER_COLUMNS = ("llm_invocation_parameters", "cvs70")
RAW_COLUMNS = ("cvs199", "cvs18", "otel_events")


def _drop_uncaptured(record: Dict[str, Any]) -> Dict[str, Any]:
    """Remove the columns of every direction that is switched off."""
    if all(_capture_flags.values()):
        return record
    drop = set(RAW_COLUMNS)
    for flag, columns in (("inputs", INPUT_COLUMNS), ("outputs", OUTPUT_COLUMNS), ("parameters", PARAMETER_COLUMNS)):
        if not _capture_flags[flag]:
            drop.update(columns)
    return {k: v for k, v in record.items() if k not in drop}


# Spans this exporter owns; everything else on a shared provider is left alone
AGENTS_SCOPES = ("traceai_openai_agents", "openinference.instrumentation.openai_agents", "openai.agents")
AGENTS_SYSTEMS = ("openai",)

# Agents-specific descriptive columns kept at ``metadata`` (agent hierarchy and
# handoff paths, model, response ids); see span2json / extract_otel_span_info.
AGENTS_METADATA_COLUMNS = frozenset({
    "cvs62",  # handoff targets (agent names)
    "cvs64",  # agent output type
    "cvs68",  # guardrail triggered
    "cvs69",  # model
    "cvs77",  # response id
    "cvs78",  # handoff from agent
    "cvs79",  # handoff to agent
    "llm_token_count",  # usage numbers (JSON)
})


class AnosysHttpExporter(SpanExporter):
    """Custom exporter to send spans to AnoSys API."""
    
    def export(self, spans) -> SpanExportResult:
        """Export spans to AnoSys API."""
        global _log_api_url
        
        for span in spans:
            if not accepts_span(span, AGENTS_SCOPES, AGENTS_SYSTEMS):
                continue
            try:
                data = extract_otel_span_info(span)
                
                span_source = data.get("from_source") or "unknown_source"
                span_name = data.get("otel_name") or data.get("name") or "unknown_name"
                logger.debug(f"[ANOSYS]📡 Exporting span from: {span_source} | Name: {span_name}")
                
                # Remove null values and empty containers
                cleaned_data = _drop_uncaptured(clean_nulls(data))
                if _pii["enabled"]:
                    cleaned_data = _redact_content(cleaned_data)
                # Level filtering, cvs198 and encryption in one place
                encrypted_data = prepare_app_record(cleaned_data, _capture_level or current_app_level()[0], AGENTS_METADATA_COLUMNS)
                if encrypted_data is None:
                    continue
                
                # size-limited, in the background: never blocks the instrumented call
                send_app_record(_log_api_url, encrypted_data)
                logger.info(f"[ANOSYS]✅ Successfully sent to backend: {span_source} | {span_name}")
                
            except Exception as e:
                logger.error("[ANOSYS] Export failed (%s)", type(e).__name__)  # no span content in logs
        
        return SpanExportResult.SUCCESS
    
    def shutdown(self):
        """Shutdown the exporter."""
        pass


def _redact_content(record: Dict[str, Any]) -> Dict[str, Any]:
    """Redact PII patterns (emails, phone numbers ...) in content columns, not in ids."""
    from anosys_sdk_core.capture import APP_METADATA_STRING_COLUMNS
    from anosys_sdk_core.redaction import redact_string

    keep = APP_METADATA_STRING_COLUMNS | AGENTS_METADATA_COLUMNS
    return {k: (redact_string(v) if isinstance(v, str) and k not in keep else v) for k, v in record.items()}


def _trace_config(pii_redaction: bool = False, **hide) -> TraceConfig:
    """TraceConfig with ``pii_redaction`` when the installed traceai supports it."""
    if pii_redaction:
        try:
            return TraceConfig(pii_redaction=True, **hide)
        except TypeError:
            logger.warning("[ANOSYS] pii_redaction is not supported by the installed "
                           "traceai-openai-agents; upgrade it to redact PII")
    return TraceConfig(**hide)


def setup_tracing(
    api_url: str, 
    use_batch_processor: bool = False, 
    config: Optional[TraceConfig] = None
) -> None:
    """
    Initialize OpenTelemetry tracing for OpenAI Agents.
    
    Args:
        api_url: URL to post telemetry data
        use_batch_processor: If True, use BatchSpanProcessor
        config: Optional TraceConfig for capture settings
    """
    global _log_api_url
    _log_api_url = api_url
    
    with _lock:
        exporter = AnosysHttpExporter()
        if use_batch_processor:
            span_processor = BatchSpanProcessor(
                exporter,
                schedule_delay_millis=1000,
                max_queue_size=2048,
                max_export_batch_size=512
            )
            logger.info("[ANOSYS] Using BatchSpanProcessor for spans")
        else:
            span_processor = SimpleSpanProcessor(exporter)
            logger.info("[ANOSYS] Using SimpleSpanProcessor for spans")
        
        # Check existing global provider
        active_provider = trace.get_tracer_provider()
        trace_provider = None
        set_global = False
        
        if isinstance(active_provider, TracerProvider):
            logger.info("[ANOSYS] Detected existing global TracerProvider. Attaching processor.")
            trace_provider = active_provider
        else:
            logger.info("[ANOSYS] Creating new global TracerProvider.")
            trace_provider = TracerProvider()
            set_global = True
        
        trace_provider.add_span_processor(span_processor)
        
        if set_global:
            trace.set_tracer_provider(trace_provider)
        
        # Instrument OpenAI Agents
        instrumentor = OpenAIAgentsInstrumentor()
        try:
            if getattr(instrumentor, "_is_instrumented_by_opentelemetry", False):
                instrumentor.uninstrument()
        except Exception as e:
            logger.warning(f"[ANOSYS]⚠️ Uninstrument warning: {e}")
        
        instrumentor.instrument(tracer_provider=trace_provider, config=config)
        logger.info("[ANOSYS]✅ AnoSys Instrumented OpenAI Agents and all OpenTelemetry traces")


class AnosysOpenAIAgentsLogger(TracingProcessor):
    """
    Logging utility that captures OpenAI Agents traces and spans,
    transforms them, and sends them to the AnoSys API.
    
    Implements the TracingProcessor interface from the OpenAI Agents SDK.
    
    Example:
        from agents import set_tracing_processor
        from anosys_sdk_openai_agents import AnosysOpenAIAgentsLogger
        
        set_tracing_processor(AnosysOpenAIAgentsLogger())
    """
    
    def __init__(
        self, 
        get_user_context: Optional[Callable] = None,
        capture_inputs: Optional[bool] = None,
        capture_outputs: Optional[bool] = None,
        capture_parameters: Optional[bool] = None,
        pii_redaction: bool = False,
        use_batch_processor: bool = False,
        capture_content: Optional[Any] = None,
    ):
        """
        Initialize the AnoSys OpenAI Agents Logger.
        
        Args:
            get_user_context: Optional function that returns user context dict
            capture_inputs: If True, capture input values
            capture_outputs: If True, capture output values
            capture_parameters: If True, capture invocation parameters
                Each defaults to None: follow ANOSYS_COLLECTION_LEVEL and a project
                ``.anosys`` file (see anosys_sdk_core.capture); full otherwise. If all
                three are False the level is metadata (no content is sent).
            pii_redaction: If True, the instrumentation redacts PII (emails, phone
                numbers ...) from captured values (default: False)
            use_batch_processor: If True, use BatchSpanProcessor
            capture_content: Optional unified level override (True/False or "full"/"metadata"/"off")
        """
        global _tracing_initialized, _capture_level

        # One level for the whole integration. The explicit flags override it;
        # turning every flag off means metadata. (OPENAI_AGENTS_DONT_LOG_* only
        # control the Agents SDK's own debug logging, not traces, so they are not used.)
        # Any flag True asks for content; all three False asks for metadata; a
        # single False only switches off its own direction (the rest follows the level).
        if capture_content is not None:
            explicit = capture_content
        else:
            given = [f for f in (capture_inputs, capture_outputs, capture_parameters) if f is not None]
            explicit = True if any(given) else (False if len(given) == 3 else None)
        _capture_level, source = resolve_app_level(explicit)
        is_full = _capture_level == FULL
        self.capture_inputs = is_full if capture_inputs is None else (capture_inputs and is_full)
        self.capture_outputs = is_full if capture_outputs is None else (capture_outputs and is_full)
        self.capture_parameters = is_full if capture_parameters is None else (capture_parameters and is_full)
        self.pii_redaction = pii_redaction
        self.capture_level = _capture_level
        _capture_flags.update(inputs=self.capture_inputs, outputs=self.capture_outputs,
                              parameters=self.capture_parameters)
        _pii["enabled"] = pii_redaction
        logger.info("[ANOSYS] OpenAI Agents collection level: %s (%s)", _capture_level, source)

        # Optional user context function
        self.get_user_context = get_user_context or (lambda: None)
        if _capture_level == OFF:
            return

        # Resolve API URL
        self.log_api_url = resolve_api_key()

        # Initialize tracing
        if not _tracing_initialized:
            setup_api(self.log_api_url)

            config = _trace_config(
                hide_inputs=not self.capture_inputs,
                hide_outputs=not self.capture_outputs,
                hide_llm_invocation_parameters=not self.capture_parameters,
                pii_redaction=pii_redaction,
            )
            
            setup_tracing(self.log_api_url, use_batch_processor=use_batch_processor, config=config)
            _tracing_initialized = True
        
    
    def _get_user_context_safe(self) -> Optional[Dict[str, Any]]:
        """Safely get user context."""
        try:
            if self.get_user_context:
                return self.get_user_context()
        except LookupError:
            pass
        return None
    
    def _log_summary(self, data: Dict[str, Any]) -> None:
        """
        Log serialized trace or span data to AnoSys.
        
        Args:
            data: Span/trace data dictionary
        """
        try:
            # Clean ContextVar objects
            cleaned_data = clean_contextvars(data)
            formatted_data = json.loads(json.dumps(cleaned_data, default=str))
            
            payload = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "data": formatted_data,
            }
            
            # Add user context if available
            user_context = self._get_user_context_safe()
            if user_context:
                payload["user_context"] = {
                    "session_id": user_context.get("session_id", "unknown_session") if isinstance(user_context, dict) else getattr(user_context, "session_id", "unknown_session"),
                    "token": user_context.get("token") if isinstance(user_context, dict) else getattr(user_context, "token", None),
                    "metadata": None,
                }
            
            # Transform and send
            transformed = span2json(payload)
            cleaned_transformed = clean_nulls(transformed)

            cleaned_transformed = _drop_uncaptured(cleaned_transformed)
            if getattr(self, "pii_redaction", False):
                cleaned_transformed = _redact_content(cleaned_transformed)
            # Level filtering (content dropped at metadata), cvs198 and encryption
            encrypted_transformed = prepare_app_record(cleaned_transformed, _capture_level or current_app_level()[0], AGENTS_METADATA_COLUMNS)
            if encrypted_transformed is None:
                return
            # size-limited, in the background: never blocks the instrumented call
            send_app_record(self.log_api_url, encrypted_transformed)
            
        except Exception as e:
            logger.error("[ANOSYS] Error logging trace (%s)", type(e).__name__)  # no span content in logs
    
    def on_trace_start(self, trace) -> None:
        """Called when a trace begins."""
        serialized_data = safe_serialize(trace)
        self._log_summary({**serialized_data, "source": "on_trace_start"})
    
    def on_trace_end(self, trace) -> None:
        """Called when a trace ends."""
        serialized_data = safe_serialize(trace)
        self._log_summary({**serialized_data, "source": "on_trace_end"})
    
    def on_span_start(self, span) -> None:
        """Called when a span starts."""
        serialized_data = safe_serialize(span)
        self._log_summary({**serialized_data, "source": "on_span_start"})
    
    def on_span_end(self, span) -> None:
        """Called when a span ends."""
        serialized_data = safe_serialize(span)
        self._log_summary({**serialized_data, "source": "on_span_end"})
    
    def force_flush(self) -> None:
        """Forces flush of all queued spans and traces."""
        pass
    
    def shutdown(self) -> None:
        """Graceful shutdown hook."""
        pass
