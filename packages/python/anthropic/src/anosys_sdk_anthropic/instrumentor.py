"""
Anthropic Instrumentor for AnoSys SDK.

Provides the main AnosysAnthropicLogger class. The Anthropic SDK reports each
API call as an OpenTelemetry span once a tracer provider is registered; this
module registers (or reuses) that provider and attaches an exporter that sends
the Anthropic spans to AnoSys.
"""

import json
import logging
import os
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
import requests

from anosys_sdk_core.config import resolve_api_key
from anosys_sdk_core.decorators import setup_api
from anosys_sdk_core.encryption import encrypt_payload
from anosys_sdk_anthropic.hooks import extract_span_info
from anosys_sdk_anthropic.mapping import ANTHROPIC_SCOPE_PREFIX

logger = logging.getLogger(__name__)

# Module-level state
_lock = threading.Lock()
_tracing_initialized = False
_log_api_url = "https://www.anosys.ai"

# Read by the Anthropic SDK when a client is constructed
CONTENT_MODE_ENV = "ANTHROPIC_OPEN_TELEMETRY_TRACES_CONTENT_MODE"


def _is_anthropic_span(span) -> bool:
    scope = getattr(span, "instrumentation_scope", None)
    return bool(scope and (scope.name or "").startswith(ANTHROPIC_SCOPE_PREFIX))


class AnosysHttpExporter(SpanExporter):
    """
    Custom exporter to send Anthropic spans to AnoSys API.

    Only spans of the Anthropic SDK's instrumentation scope are exported, so
    attaching it to a shared provider does not duplicate other integrations.
    """

    def __init__(self, get_user_context: Optional[Callable] = None):
        self._get_user_context = get_user_context or (lambda: None)

    def export(self, spans) -> SpanExportResult:
        """Export spans to AnoSys API."""
        global _log_api_url

        for span in spans:
            if not _is_anthropic_span(span):
                continue
            try:
                span_json = json.loads(span.to_json(indent=2))
                data = extract_span_info(span_json)

                # Attach user context if available
                try:
                    user_context = self._get_user_context()
                    if user_context:
                        data["cvs5"] = json.dumps({
                            "session_id": (user_context.get("session_id", "unknown_session")
                                           if isinstance(user_context, dict)
                                           else getattr(user_context, "session_id", "unknown_session")),
                            "token": (user_context.get("token")
                                      if isinstance(user_context, dict)
                                      else getattr(user_context, "token", None)),
                        })
                except Exception:
                    pass

                logger.debug("Exporting span from: %s | Name: %s", data.get("cvs200"), data.get("otel_name"))

                data = encrypt_payload(data)
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
    Initialize OpenTelemetry tracing for Anthropic.

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
        if isinstance(active_provider, TracerProvider):
            logger.info("Detected existing global TracerProvider. Attaching processor.")
            active_provider.add_span_processor(span_processor)
        else:
            logger.info("Creating new global TracerProvider.")
            trace_provider = TracerProvider()
            trace_provider.add_span_processor(span_processor)
            trace.set_tracer_provider(trace_provider)

        logger.info("AnoSys attached to Anthropic OpenTelemetry traces")


class AnosysAnthropicLogger:
    """
    Logging utility that captures Anthropic (Claude) API calls, transforms them,
    and sends them to the AnoSys API endpoint for ingestion/logging.

    Example:
        from anosys_sdk_anthropic import AnosysAnthropicLogger
        import anthropic

        AnosysAnthropicLogger()  # Initialize once, before creating clients
        client = anthropic.Anthropic()
        message = client.messages.create(...)
    """

    def __init__(
        self,
        get_user_context: Optional[Callable] = None,
        capture_content: bool = True,
        use_batch_processor: bool = False,
    ):
        """
        Initialize the AnoSys Anthropic Logger.

        Args:
            get_user_context: Optional function that returns user context dict
            capture_content: If True, record prompts and completions (default: True).
                Applies to clients created afterwards that are given no
                ``open_telemetry`` option of their own.
            use_batch_processor: If True, use BatchSpanProcessor
        """
        global _tracing_initialized

        # Resolve API URL
        self.log_api_url = resolve_api_key()

        # Optional user context function
        self.get_user_context = get_user_context or (lambda: None)

        # The SDK records metadata only unless content mode is requested
        if capture_content and os.getenv(CONTENT_MODE_ENV) is None:
            os.environ[CONTENT_MODE_ENV] = "content"

        # Initialize tracing if not already done
        if not _tracing_initialized:
            setup_api(self.log_api_url)
            setup_tracing(
                self.log_api_url,
                use_batch_processor=use_batch_processor,
                get_user_context=self.get_user_context,
            )
            _tracing_initialized = True
