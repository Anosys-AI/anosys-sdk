<p align="center">
  <a href="https://anosys.ai">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/anosys-ai/anosys-sdk/main/assets/anosys-new-white-darkmode.svg">
      <img src="https://raw.githubusercontent.com/anosys-ai/anosys-sdk/main/assets/anosys-new-black-lightmode.svg" alt="Anosys.ai" width="240">
    </picture>
  </a>
</p>

# AnoSys SDK for Anthropic

Automatically capture and send Anthropic (Claude) API calls to [AnoSys](https://anosys.ai) for monitoring, analytics, and observability.

## Features

- **Native Instrumentation** - Uses the OpenTelemetry spans the Anthropic SDK emits itself; no third-party instrumentor
- **Streaming Support** - `messages.stream()` and `stream=True` calls are captured with final usage
- **OpenTelemetry Semantic Conventions** - Follows Gen AI standards, same columns as the OpenAI integration
- **Prompt caching and thinking** - Cache read/write tokens and available extended-thinking content are tracked

## Installation

Requires Python 3.10 or later.

```bash
pip install anosys-sdk-anthropic
```

Requires `anthropic>=2.0.0`.

## Quick Start

```python
import os
import anthropic
from anosys_sdk_anthropic import AnosysAnthropicLogger

os.environ["ANTHROPIC_API_KEY"] = "your-anthropic-key"
os.environ["ANOSYS_API_KEY"] = "your-anosys-key"

# Initialize (do once at startup, before creating clients)
AnosysAnthropicLogger()

# Use Anthropic normally - instrumented calls are logged
client = anthropic.Anthropic()

message = client.messages.create(
    model="claude-sonnet-5-5",
    max_tokens=1024,
    system="You are a helpful assistant.",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(message.content[0].text)
```

## Options

```python
AnosysAnthropicLogger(
    get_user_context=lambda: {"session_id": "abc", "token": "user-token"},
    capture_content=True,       # record prompts and completions (default)
    use_batch_processor=False,  # BatchSpanProcessor instead of SimpleSpanProcessor
)
```

`capture_content` sets `ANTHROPIC_OPEN_TELEMETRY_TRACES_CONTENT_MODE=content` when it is not already set. The SDK reads it when a client is constructed, so create clients after the logger. A client given its own `open_telemetry` option uses that option instead, and the SDK treats it as complete: `open_telemetry={"tracer_provider": provider}` alone silently switches the client to metadata-only. When you need to pass an option, start from `get_anthropic_open_telemetry_options()`, which keeps the active provider and your `capture_content` choice:

```python
from anosys_sdk_anthropic import get_anthropic_open_telemetry_options

client = anthropic.Anthropic(open_telemetry={**get_anthropic_open_telemetry_options(), "conversation_id": "abc"})
```

If your application already registers an OpenTelemetry `TracerProvider`, the logger attaches to it. It sends the Anthropic SDK's spans plus any GenAI spans your code creates around them (spans with a `gen_ai.operation.name`, such as an agent loop or tool calls, as in the support-copilot notebook); other spans on the provider are skipped.

## What Data is Captured?

Following [OpenTelemetry Gen AI standards](https://opentelemetry.io/docs/specs/semconv/gen-ai/):

- `gen_ai.system` / `gen_ai.provider.name` - Always "anthropic"
- `gen_ai.request.model`, `gen_ai.request.max_tokens`, `gen_ai.request.stop_sequences`
- `gen_ai.response.model`, `gen_ai.response.id`, `gen_ai.response.finish_reasons` (stop reason)
- `gen_ai.usage.input_tokens` (including cached tokens), `gen_ai.usage.output_tokens`, `gen_ai.usage.total_tokens`
- Prompt cache tokens (`cvn4` read, `cvn5` write) and extended thinking (`cvb3`)
- System instructions, input and output messages
- Timestamps, duration, errors

Records are tagged `cvs200 = "AnthropicTelemetry"`. See [MAPPINGS.md](../../../docs/MAPPINGS.md) for the column map.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANOSYS_API_KEY` | Yes | Your AnoSys API key |
| `ANTHROPIC_API_KEY` | Yes | Your Anthropic API key |

## License

Apache 2.0

## Content controls

See the [content-controls reference](../../../docs/DATA_CONTROLS.md) for encryption coverage, default columns, size limits, and limitations. Encryption is opt-in and applies to selected string fields; it does not encrypt the complete record.

Collection follows one level for every AnoSys SDK: `ANOSYS_COLLECTION_LEVEL=full` (default), `metadata` (no prompts, completions or tool data) or `off`, a project `.anosys` file can only lower it, and `ANOSYS_DISABLE=1` stops all sending. Without an API key nothing is sent. Telemetry is sent in the background and never delays your calls. See the [data-collection policy](../../../PRIVACY.md).
