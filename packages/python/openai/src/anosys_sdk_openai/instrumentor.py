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
from traceai_openai import OpenAIInstrumentor
import requests

from anosys_sdk_core.config import resolve_api_key
from anosys_sdk_core.decorators import setup_api
from anosys_sdk_openai.hooks import extract_span_info

logger = logging.getLogger(__name__)

# Module-level state
_lock = threading.Lock()
_tracing_initialized = False
_log_api_url = "https://www.anosys.ai"


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
            try:
                span_json = json.loads(span.to_json(indent=2))
                data = extract_span_info(span_json)

                # Attach user context if available
                try:
                    user_context = self._get_user_context()
                    if user_context:
                        data["user_context"] = {
                            "session_id": (user_context.get("session_id", "unknown_session")
                                           if isinstance(user_context, dict)
                                           else getattr(user_context, "session_id", "unknown_session")),
                            "token": (user_context.get("token")
                                      if isinstance(user_context, dict)
                                      else getattr(user_context, "token", None)),
                        }
                except Exception:
                    pass

                span_source = data.get("cvs200") or "unknown_source"
                span_name = data.get("otel_name") or "unknown"
                logger.debug("Exporting span from: %s | Name: %s", span_source, span_name)

                response = requests.post(_log_api_url, json=data, timeout=5)
                response.raise_for_status()

            except requests.exceptions.HTTPError as e:
                logger.error("HTTP export failed (%s): %s", e.response.status_code, e)
            except Exception as e:
                logger.error("Export failed: %s", e)

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

        instrumentor.instrument(tracer_provider=trace_provider)
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
    
    def __init__(self, get_user_context: Optional[Callable] = None):
        """
        Initialize the AnoSys OpenAI Logger.
        
        Args:
            get_user_context: Optional function that returns user context dict
        """
        global _tracing_initialized
        
        # Resolve API URL
        self.log_api_url = resolve_api_key()
        
        # Optional user context function
        self.get_user_context = get_user_context or (lambda: None)
        
        # Initialize tracing if not already done
        if not _tracing_initialized:
            setup_api(self.log_api_url)
            setup_tracing(self.log_api_url, get_user_context=self.get_user_context)
            _tracing_initialized = True
