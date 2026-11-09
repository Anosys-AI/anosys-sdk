"""
Claude Agent SDK instrumentation for AnoSys SDK.

Provides the AnosysClaudeAgentsLogger class. It wraps ``claude_agent_sdk.query``
and ``ClaudeSDKClient.receive_response`` so that every agent run produces
OpenTelemetry spans (see ``tracer.AgentRunTracer``), and exports those spans to
AnoSys.
"""

import functools
import json
import logging
import sys
import threading
from typing import Any, AsyncIterable, AsyncIterator, Callable, Optional

from opentelemetry import context as otel_context
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
from anosys_sdk_core.transport import post_record
from anosys_sdk_claude_agents.hooks import extract_span_info
from anosys_sdk_claude_agents.mapping import CLAUDE_AGENTS_SCOPE
from anosys_sdk_claude_agents.tracer import AgentRunTracer

logger = logging.getLogger(__name__)

# Module-level state
_lock = threading.Lock()
_tracing_initialized = False
_log_api_url = "https://www.anosys.ai"
_tracer: Optional[trace.Tracer] = None
_run_settings = {"capture_content": True, "emit_llm_spans": False, "agent_name": None}
_originals: dict = {}


class AnosysHttpExporter(SpanExporter):
    """
    Custom exporter to send Claude Agent SDK spans to AnoSys API.

    Only spans of this package's instrumentation scope are exported, so
    attaching it to a shared provider does not duplicate other integrations.
    """

    def __init__(self, get_user_context: Optional[Callable] = None):
        self._get_user_context = get_user_context or (lambda: None)

    def export(self, spans) -> SpanExportResult:
        """Export spans to AnoSys API."""
        global _log_api_url

        for span in spans:
            scope = getattr(span, "instrumentation_scope", None)
            if not scope or scope.name != CLAUDE_AGENTS_SCOPE:
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

                from anosys_sdk_core.privacy import CONSENT_COLUMN, CONSENT_FIELD, FULL, METADATA, consent_value
                level = FULL if _capture_content else METADATA
                val = consent_value(level)
                data[CONSENT_FIELD] = val
                data[CONSENT_COLUMN] = val

                data = encrypt_payload(data)
                # fitted under ANOSYS_MAX_BATCH_BYTES; None when too large even after truncation
                response = post_record(_log_api_url, data, timeout=5)
                if response is not None:
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
    Initialize OpenTelemetry tracing for the Claude Agent SDK.

    Args:
        api_url: URL to post telemetry data
        use_batch_processor: If True, use BatchSpanProcessor; otherwise SimpleSpanProcessor
        get_user_context: Optional callable that returns user context dict
    """
    global _log_api_url, _tracer
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
            trace_provider = active_provider
        else:
            logger.info("Creating new global TracerProvider.")
            trace_provider = TracerProvider()
            trace.set_tracer_provider(trace_provider)
        trace_provider.add_span_processor(span_processor)

        _tracer = trace_provider.get_tracer(CLAUDE_AGENTS_SCOPE)
        _instrument()
        logger.info("AnoSys instrumented the Claude Agent SDK")


# ── run tracing ───────────────────────────────────────────────────────────────

async def trace_messages(
    messages: AsyncIterable[Any],
    prompt: Any = None,
    options: Any = None,
) -> AsyncIterator[Any]:
    """
    Trace one agent run from the messages it yields, re-yielding each message.

    Use it for entry points that are not wrapped automatically:

        async for message in trace_messages(some_stream(), prompt=prompt, options=options):
            ...
    """
    if _tracer is None:
        async for message in messages:
            yield message
        return

    run = AgentRunTracer(
        _tracer,
        prompt=prompt,
        options=options,
        agent_name=_run_settings["agent_name"],
        capture_content=_run_settings["capture_content"],
        emit_llm_spans=_run_settings["emit_llm_spans"],
    )
    iterator = messages.__aiter__()
    error: Optional[BaseException] = None
    try:
        while True:
            # The run span is current while the SDK works, so the Claude Code
            # subprocess it starts inherits the trace context (TRACEPARENT).
            token = otel_context.attach(trace.set_span_in_context(run.root))
            try:
                message = await iterator.__anext__()
            except StopAsyncIteration:
                break
            finally:
                otel_context.detach(token)
            run.on_message(message)
            yield message
    except BaseException as e:  # noqa: B036 - recorded on the span, then re-raised
        if not isinstance(e, GeneratorExit):
            error = e
        raise
    finally:
        run.finish(error)
        # Stop the SDK's stream too when the caller stops early or fails
        aclose = getattr(iterator, "aclose", None)
        if aclose is not None:
            try:
                await aclose()
            except Exception:
                pass


def wrap_query(query_fn: Callable[..., AsyncIterator[Any]]) -> Callable[..., AsyncIterator[Any]]:
    """Wrap a ``query()`` function so that each call is traced."""
    if getattr(query_fn, "__anosys_wrapped__", False):
        return query_fn

    @functools.wraps(query_fn)
    def traced_query(*args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        return trace_messages(
            query_fn(*args, **kwargs),
            prompt=kwargs.get("prompt", args[0] if args else None),
            options=kwargs.get("options"),
        )

    traced_query.__anosys_wrapped__ = True
    return traced_query


def _instrument() -> None:
    """Patch the Agent SDK entry points (idempotent)."""
    try:
        import claude_agent_sdk
        from claude_agent_sdk import ClaudeSDKClient
    except ImportError:
        logger.warning("claude-agent-sdk is not installed; nothing to instrument")
        return

    if "query" not in _originals:
        original_query = claude_agent_sdk.query
        _originals["query"] = original_query
        traced = wrap_query(original_query)
        claude_agent_sdk.query = traced
        query_module = sys.modules.get("claude_agent_sdk.query")
        if query_module is not None and getattr(query_module, "query", None) is original_query:
            query_module.query = traced

    if "client.query" not in _originals:
        original_client_query = ClaudeSDKClient.query
        original_receive_response = ClaudeSDKClient.receive_response
        _originals["client.query"] = original_client_query
        _originals["client.receive_response"] = original_receive_response

        @functools.wraps(original_client_query)
        async def client_query(self, prompt, *args, **kwargs):
            self._anosys_prompt = prompt
            return await original_client_query(self, prompt, *args, **kwargs)

        @functools.wraps(original_receive_response)
        def receive_response(self, *args, **kwargs):
            return trace_messages(
                original_receive_response(self, *args, **kwargs),
                prompt=getattr(self, "_anosys_prompt", None),
                options=getattr(self, "options", None),
            )

        ClaudeSDKClient.query = client_query
        ClaudeSDKClient.receive_response = receive_response


def uninstrument() -> None:
    """Restore the original Agent SDK entry points."""
    try:
        import claude_agent_sdk
        from claude_agent_sdk import ClaudeSDKClient
    except ImportError:
        return
    if "query" in _originals:
        original_query = _originals.pop("query")
        claude_agent_sdk.query = original_query
        query_module = sys.modules.get("claude_agent_sdk.query")
        if query_module is not None and hasattr(query_module, "query"):
            query_module.query = original_query
    if "client.query" in _originals:
        ClaudeSDKClient.query = _originals.pop("client.query")
        ClaudeSDKClient.receive_response = _originals.pop("client.receive_response")


class AnosysClaudeAgentsLogger:
    """
    Logging utility that captures Claude Agent SDK runs (agent, tool and
    subagent spans), transforms them, and sends them to the AnoSys API.

    Example:
        from anosys_sdk_claude_agents import AnosysClaudeAgentsLogger

        AnosysClaudeAgentsLogger()  # Initialize once, before importing query

        from claude_agent_sdk import query
        async for message in query(prompt="..."):
            ...
    """

    def __init__(
        self,
        get_user_context: Optional[Callable] = None,
        agent_name: Optional[str] = None,
        capture_content: bool = True,
        emit_llm_spans: bool = False,
        use_batch_processor: bool = False,
    ):
        """
        Initialize the AnoSys Claude Agents Logger.

        Args:
            get_user_context: Optional function that returns user context dict
            agent_name: Name recorded as gen_ai.agent.name (default: "claude_agent")
            capture_content: If True, record prompts, results and tool input/output (default: True)
            emit_llm_spans: If True, also emit one chat span per assistant response.
                Usage totals stay on the agent span; chat spans carry per-call usage.
            use_batch_processor: If True, use BatchSpanProcessor
        """
        global _tracing_initialized

        # Resolve API URL
        self.log_api_url = resolve_api_key()

        # Optional user context function
        self.get_user_context = get_user_context or (lambda: None)

        _run_settings.update(
            capture_content=capture_content,
            emit_llm_spans=emit_llm_spans,
            agent_name=agent_name,
        )

        # Initialize tracing if not already done
        if not _tracing_initialized:
            setup_api(self.log_api_url)
            setup_tracing(
                self.log_api_url,
                use_batch_processor=use_batch_processor,
                get_user_context=self.get_user_context,
            )
            _tracing_initialized = True
