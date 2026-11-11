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

from anosys_sdk_core.config import resolve_api_key
from anosys_sdk_core.decorators import setup_api
from anosys_sdk_core.capture import current_app_level, prepare_app_record, resolve_app_level, user_context_value
from anosys_sdk_core.privacy import FULL, OFF
from anosys_sdk_core.transport import send_app_record
from anosys_sdk_anthropic.hooks import extract_span_info
from anosys_sdk_anthropic.mapping import ANTHROPIC_SCOPE_PREFIX, CLAUDE_AGENTS_SCOPE

logger = logging.getLogger(__name__)

# Module-level state
_lock = threading.Lock()
_tracing_initialized = False
_log_api_url = ""  # set by setup_tracing; empty = nothing is sent
_capture_content = True
_capture_level = None  # set by AnosysAnthropicLogger; until then the shared level applies (anosys_sdk_core.capture)

# Read by the Anthropic SDK when a client is constructed
CONTENT_MODE_ENV = "ANTHROPIC_OPEN_TELEMETRY_TRACES_CONTENT_MODE"


_NON_ANTHROPIC_SCOPE_PREFIXES = (
    "traceai_",
    "openinference.instrumentation.",
    "opentelemetry.instrumentation.openai",
    "@opentelemetry/instrumentation-openai",
    "openai",
)


def _is_anthropic_span(span) -> bool:
    """Spans this exporter sends: the Anthropic SDK's own spans, plus GenAI
    spans the application creates around them (agent loops, tool calls), which
    carry ``gen_ai.operation.name``. Other spans on a shared provider are skipped."""
    scope = getattr(span, "instrumentation_scope", None) or getattr(span, "instrumentation_info", None)
    scope_name = str(getattr(scope, "name", "") or "") if scope else ""
    if scope_name.startswith(ANTHROPIC_SCOPE_PREFIX):
        return True
    if scope_name == CLAUDE_AGENTS_SCOPE or scope_name.startswith(_NON_ANTHROPIC_SCOPE_PREFIXES):
        return False
    attributes = getattr(span, "attributes", None) or {}
    if "gen_ai.operation.name" not in attributes:
        return False
    system = str(
        attributes.get("gen_ai.provider.name")
        or attributes.get("gen_ai.system")
        or attributes.get("llm.system")
        or ""
    ).lower()
    return not system or system == "anthropic"


class AnosysHttpExporter(SpanExporter):
    """
    Custom exporter to send Anthropic spans to AnoSys API.

    Exports the Anthropic SDK's spans and application GenAI spans (see
    ``_is_anthropic_span``); unrelated spans on a shared provider are skipped.
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
                    user_ctx = self._get_user_context()
                    value = user_context_value(user_ctx)
                    if value:
                        data["cvs5"] = value
                except Exception:
                    pass

                logger.debug("Exporting span from: %s | Name: %s", data.get("cvs200"), data.get("otel_name"))

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


def get_anthropic_open_telemetry_options() -> dict:
    """
    Recommended ``open_telemetry`` option for ``anthropic.Anthropic(open_telemetry=...)``.

    The SDK treats a given option as complete and ignores the environment, so a
    hand-written option such as ``{"tracer_provider": ...}`` silently switches the
    client to metadata-only. This carries the active tracer provider and the
    logger's ``capture_content`` choice. Call it after creating the logger.
    """
    options: dict = {"traces": {"content_mode": "content" if _capture_content else "metadata_only"}}
    provider = trace.get_tracer_provider()
    if isinstance(provider, TracerProvider):
        options["tracer_provider"] = provider
    else:
        logger.warning("get_anthropic_open_telemetry_options() was called before AnosysAnthropicLogger")
    return options


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
        capture_content: Optional[bool] = None,
        use_batch_processor: bool = False,
    ):
        """
        Initialize the AnoSys Anthropic Logger.

        Args:
            get_user_context: Optional function that returns user context dict
            capture_content: True to record prompts and completions, False for
                metadata only. None (default) follows ANOSYS_COLLECTION_LEVEL and a
                project ``.anosys`` file (see anosys_sdk_core.capture); full otherwise.
                Applies to clients created afterwards that are given no
                ``open_telemetry`` option of their own.
            use_batch_processor: If True, use BatchSpanProcessor
        """
        global _tracing_initialized, _capture_content, _capture_level, _log_api_url

        _capture_level, source = resolve_app_level(capture_content)
        _capture_content = _capture_level == FULL
        self.capture_level = _capture_level
        logger.info("AnoSys Anthropic collection level: %s (%s)", _capture_level, source)
        if _capture_level == OFF:
            return

        # Resolve API URL
        self.log_api_url = resolve_api_key()
        if self.log_api_url:
            _log_api_url = self.log_api_url
            setup_api(self.log_api_url)

        # Optional user context function
        self.get_user_context = get_user_context or (lambda: None)

        # The SDK records metadata only unless content mode is requested
        if _capture_content and os.getenv(CONTENT_MODE_ENV) is None:
            os.environ[CONTENT_MODE_ENV] = "content"

        # Initialize tracing if not already done
        if not _tracing_initialized:
            setup_tracing(
                self.log_api_url,
                use_batch_processor=use_batch_processor,
                get_user_context=self.get_user_context,
            )
            _tracing_initialized = True
