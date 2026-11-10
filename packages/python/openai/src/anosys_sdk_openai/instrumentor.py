"""
OpenAI Instrumentor for AnoSys SDK.

Provides the main AnosysOpenAILogger class that instruments OpenAI API calls
using OpenTelemetry and sends traces to AnoSys.
"""

import json
import logging
import threading
from typing import Callable, Optional

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
try:
    from fi_instrumentation.fi_types import SpanAttributes
    _GENAI_FALLBACKS = {
        "GEN_AI_INPUT_MESSAGES": "gen_ai.input.messages",
        "GEN_AI_OUTPUT_MESSAGES": "gen_ai.output.messages",
        "GEN_AI_PROMPTS": "gen_ai.prompts",
        "GEN_AI_PROVIDER_NAME": "gen_ai.provider.name",
        "GEN_AI_REQUEST_MODEL": "gen_ai.request.model",
        "GEN_AI_REQUEST_PARAMETERS": "gen_ai.request.parameters",
        "GEN_AI_SPAN_KIND": "gen_ai.span.kind",
        "GEN_AI_TOOL_DEFINITIONS": "gen_ai.tool.definitions",
        "GEN_AI_USAGE_INPUT_TOKENS": "gen_ai.usage.input_tokens",
        "GEN_AI_USAGE_INPUT_TOKENS_CACHE_READ": "gen_ai.usage.input_tokens.cache_read",
        "GEN_AI_USAGE_OUTPUT_TOKENS": "gen_ai.usage.output_tokens",
        "GEN_AI_USAGE_OUTPUT_TOKENS_REASONING": "gen_ai.usage.output_tokens.reasoning",
        "GEN_AI_USAGE_TOTAL_TOKENS": "gen_ai.usage.total_tokens",
    }
    for attr, val in _GENAI_FALLBACKS.items():
        if not hasattr(SpanAttributes, attr):
            setattr(SpanAttributes, attr, val)
except Exception:
    pass

from traceai_openai import OpenAIInstrumentor

from anosys_sdk_core.config import resolve_api_key
from anosys_sdk_core.decorators import setup_api
from anosys_sdk_core.capture import accepts_span, current_app_level, prepare_app_record, resolve_app_level, user_context_value
from anosys_sdk_core.privacy import METADATA, OFF
from anosys_sdk_core.transport import send_app_record
from anosys_sdk_openai.hooks import extract_span_info

logger = logging.getLogger(__name__)

# Module-level state
_lock = threading.Lock()
_tracing_initialized = False
_log_api_url = ""  # set by setup_tracing; empty = nothing is sent

# Spans this exporter owns; everything else on a shared provider is left alone
OPENAI_SCOPES = ("traceai_openai", "openinference.instrumentation.openai", "opentelemetry.instrumentation.openai")
OPENAI_SYSTEMS = ("openai",)
_capture_level = None  # set by AnosysOpenAILogger; until then the shared level applies (anosys_sdk_core.capture)


class AnosysHttpExporter(SpanExporter):
    """
    Custom exporter to send spans to AnoSys API.

    Converts OpenTelemetry spans to AnoSys format and posts them
    to the configured API endpoint.
    """

    def __init__(self, get_user_context: Optional[Callable] = None):
        self._get_user_context = get_user_context or (lambda: None)

    def export(self, spans) -> SpanExportResult:
        """Export spans to AnoSys API."""
        global _log_api_url

        for span in spans:
            if not accepts_span(span, OPENAI_SCOPES, OPENAI_SYSTEMS):
                continue
            try:
                span_json = json.loads(span.to_json(indent=2))
                data = extract_span_info(span_json)

                # Attach user context if available
                try:
                    value = user_context_value(self._get_user_context())
                    if value:
                        data["cvs5"] = value
                except Exception:
                    pass

                span_source = data.get("cvs200") or "unknown_source"
                span_name = data.get("otel_name") or "unknown"
                logger.debug("Exporting span from: %s | Name: %s", span_source, span_name)

                # Level filtering, cvs198 and encryption in one place
                data = prepare_app_record(data, _capture_level or current_app_level()[0])
                if data is None:
                    continue
                # size-limited, in the background: never blocks the instrumented call
                send_app_record(_log_api_url, data)

            except Exception as e:
                logger.error("AnoSys export failed (%s)", type(e).__name__)  # no span content in logs

        return SpanExportResult.SUCCESS

    def shutdown(self):
        pass


def setup_tracing(
    api_url: str,
    use_batch_processor: bool = False,
    get_user_context: Optional[Callable] = None,
) -> None:
    """
    Initialize OpenTelemetry tracing for OpenAI.

    Args:
        api_url: URL to post telemetry data
        use_batch_processor: If True, use BatchSpanProcessor; otherwise SimpleSpanProcessor
        get_user_context: Optional callable that returns user context dict
    """
    global _log_api_url
    _log_api_url = api_url

    with _lock:
        exporter = AnosysHttpExporter(get_user_context=get_user_context)
        if use_batch_processor:
            span_processor = BatchSpanProcessor(
                exporter,
                schedule_delay_millis=1000,
                max_queue_size=2048,
                max_export_batch_size=512,
            )
            logger.info("Using BatchSpanProcessor for spans")
        else:
            span_processor = SimpleSpanProcessor(exporter)
            logger.info("Using SimpleSpanProcessor for spans")

        active_provider = trace.get_tracer_provider()
        trace_provider = None
        set_global = False

        if isinstance(active_provider, TracerProvider):
            logger.info("Detected existing global TracerProvider. Attaching processor.")
            trace_provider = active_provider
        else:
            logger.info("Creating new global TracerProvider.")
            trace_provider = TracerProvider()
            set_global = True

        trace_provider.add_span_processor(span_processor)

        if set_global:
            trace.set_tracer_provider(trace_provider)

        instrumentor = OpenAIInstrumentor()
        try:
            if getattr(instrumentor, "_is_instrumented_by_opentelemetry", False):
                instrumentor.uninstrument()
        except Exception as e:
            logger.warning("Uninstrument warning: %s", e)

        instrument_kwargs = {"tracer_provider": trace_provider}
        if (_capture_level or current_app_level()[0]) == METADATA:
            # Defense in depth: ask the instrumentation not to record content either
            try:
                from traceai_openai import TraceConfig
                instrument_kwargs["config"] = TraceConfig(hide_inputs=True, hide_outputs=True)
            except ImportError:
                pass
        instrumentor.instrument(**instrument_kwargs)
        logger.info("AnoSys instrumented OpenAI and OpenTelemetry traces")


class AnosysOpenAILogger:
    """
    Logging utility that captures OpenAI traces and spans, transforms them,
    and sends them to the AnoSys API endpoint for ingestion/logging.
    
    Example:
        from anosys_sdk_openai import AnosysOpenAILogger
        from openai import OpenAI
        
        AnosysOpenAILogger()  # Initialize once
        client = OpenAI()
        response = client.chat.completions.create(...)
    """
    
    def __init__(self, get_user_context: Optional[Callable] = None, capture_content: Optional[bool] = None):
        """
        Initialize the AnoSys OpenAI Logger.
        
        Args:
            get_user_context: Optional function that returns user context dict
            capture_content: True to send prompts and completions, False for
                metadata only. None (default) follows ANOSYS_COLLECTION_LEVEL and a
                project ``.anosys`` file (see anosys_sdk_core.capture); full otherwise.
        """
        global _tracing_initialized, _capture_level, _log_api_url

        _capture_level, source = resolve_app_level(capture_content)
        self.capture_level = _capture_level
        logger.info("AnoSys OpenAI collection level: %s (%s)", _capture_level, source)
        if _capture_level == OFF:
            return
        
        # Resolve API URL
        self.log_api_url = resolve_api_key()
        if self.log_api_url:
            _log_api_url = self.log_api_url
            setup_api(self.log_api_url)
        
        # Optional user context function
        self.get_user_context = get_user_context or (lambda: None)
        
        # Initialize tracing if not already done
        if not _tracing_initialized:
            setup_tracing(self.log_api_url, get_user_context=self.get_user_context)
            _tracing_initialized = True
