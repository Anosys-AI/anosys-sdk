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
from traceai_openai_agents import OpenAIAgentsInstrumentor
import requests

from agents import TracingProcessor

from anosys_sdk_core.config import resolve_api_key
from anosys_sdk_core.decorators import setup_api
from anosys_sdk_core.context import clean_contextvars
from anosys_sdk_openai_agents.mapping import span2json, extract_otel_span_info
from anosys_sdk_openai_agents.utils import safe_serialize

# Set up logging
logger = logging.getLogger(__name__)

# Module-level state
_lock = threading.Lock()
_tracing_initialized = False
_log_api_url = "https://www.anosys.ai"


class AnosysHttpExporter(SpanExporter):
    """Custom exporter to send spans to AnoSys API."""
    
    def export(self, spans) -> SpanExportResult:
        """Export spans to AnoSys API."""
        global _log_api_url
        
        for span in spans:
            try:
                data = extract_otel_span_info(span)
                
                span_source = data.get("from_source") or "unknown_source"
                span_name = data.get("otel_name") or data.get("name") or "unknown_name"
                logger.debug(f"[ANOSYS]📡 Exporting span from: {span_source} | Name: {span_name}")
                
                # Remove null values
                cleaned_data = {k: v for k, v in data.items() if v is not None}
                
                response = requests.post(_log_api_url, json=cleaned_data, timeout=5)
                response.raise_for_status()
                logger.info(f"[ANOSYS]✅ Successfully sent to backend: {span_source} | {span_name}")
                
            except requests.exceptions.HTTPError as e:
                logger.error(f"[ANOSYS]❌ HTTP Export failed ({e.response.status_code}): {e}")
            except Exception as e:
                logger.error(f"[ANOSYS]❌ Export failed: {e}")
        
        return SpanExportResult.SUCCESS
    
    def shutdown(self):
        """Shutdown the exporter."""
        pass


def setup_tracing(api_url: str, use_batch_processor: bool = False) -> None:
    """
    Initialize OpenTelemetry tracing for OpenAI Agents.
    
    Args:
        api_url: URL to post telemetry data
        use_batch_processor: If True, use BatchSpanProcessor
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
        
        instrumentor.instrument(tracer_provider=trace_provider)
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
    
    def __init__(self, get_user_context: Optional[Callable] = None):
        """
        Initialize the AnoSys OpenAI Agents Logger.
        
        Args:
            get_user_context: Optional function that returns user context dict
        """
        global _tracing_initialized
        
        # Resolve API URL
        self.log_api_url = resolve_api_key()
        
        # Initialize tracing
        if not _tracing_initialized:
            setup_api(self.log_api_url)
            setup_tracing(self.log_api_url)
            _tracing_initialized = True
        
        # Optional user context function
        self.get_user_context = get_user_context or (lambda: None)
    
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
            response = requests.post(self.log_api_url, json=transformed, timeout=5)
            response.raise_for_status()
            
        except Exception as e:
            print(f"[Logger]❌ Error logging trace: {e}")
    
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
