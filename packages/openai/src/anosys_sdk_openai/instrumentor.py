"""
OpenAI Instrumentor for AnoSys SDK.

Provides the main AnosysOpenAILogger class that instruments OpenAI API calls
using OpenTelemetry and sends traces to AnoSys.
"""

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
import json

from anosys_sdk_core.config import resolve_api_key
from anosys_sdk_core.decorators import setup_api
from anosys_sdk_openai.hooks import extract_span_info


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
    
    def export(self, spans) -> SpanExportResult:
        """Export spans to AnoSys API."""
        global _log_api_url
        
        for span in spans:
            try:
                # Convert span to JSON and extract info
                span_json = json.loads(span.to_json(indent=2))
                data = extract_span_info(span_json)
                
                # Log source info
                span_source = data.get("cvs200") or "unknown_source"
                span_name = data.get("otel_name") or "unknown"
                print(f"[ANOSYS]📡 Exporting span from: {span_source} | Name: {span_name}")
                
                response = requests.post(_log_api_url, json=data, timeout=5)
                response.raise_for_status()
                
            except Exception as e:
                print(f"[ANOSYS]❌ Export failed: {e}")
                try:
                    print(f"[ANOSYS]❌ Data: {json.dumps(data, indent=2)}")
                except Exception:
                    pass
        
        return SpanExportResult.SUCCESS
    
    def shutdown(self):
        """Shutdown the exporter."""
        pass


def setup_tracing(api_url: str, use_batch_processor: bool = False) -> None:
    """
    Initialize OpenTelemetry tracing for OpenAI.
    
    Args:
        api_url: URL to post telemetry data
        use_batch_processor: If True, use BatchSpanProcessor; otherwise SimpleSpanProcessor
    """
    global _log_api_url
    _log_api_url = api_url
    
    with _lock:
        # Create tracer provider
        trace_provider = TracerProvider()
        
        # Create exporter and processor
        exporter = AnosysHttpExporter()
        if use_batch_processor:
            span_processor = BatchSpanProcessor(
                exporter,
                schedule_delay_millis=1000,
                max_queue_size=2048,
                max_export_batch_size=512
            )
            print("[ANOSYS] Using BatchSpanProcessor for spans")
        else:
            span_processor = SimpleSpanProcessor(exporter)
            print("[ANOSYS] Using SimpleSpanProcessor for spans")
        
        # Register global provider
        trace_provider.add_span_processor(span_processor)
        trace.set_tracer_provider(trace_provider)
        
        # Instrument OpenAI
        instrumentor = OpenAIInstrumentor()
        try:
            if getattr(instrumentor, "_is_instrumented_by_opentelemetry", False):
                instrumentor.uninstrument()
        except Exception as e:
            print(f"[ANOSYS]⚠️ Uninstrument warning: {e}")
        
        instrumentor.instrument(tracer_provider=trace_provider)
        
        print("[ANOSYS]✅ AnoSys Instrumented OpenAI and all OpenTelemetry traces")
        
        # Print active tracer info
        active_provider = trace.get_tracer_provider()
        print(f"[ANOSYS] Active global tracer provider: {active_provider.__class__.__name__}")


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
        
        # Reset flag for fresh initialization
        _tracing_initialized = False
        
        # Resolve API URL
        self.log_api_url = resolve_api_key()
        
        # Optional user context function
        self.get_user_context = get_user_context or (lambda: None)
        
        # Initialize tracing if not already done
        if not _tracing_initialized:
            setup_api(self.log_api_url)
            setup_tracing(self.log_api_url)
            _tracing_initialized = True
