# AnoSys SDK for OpenAI

Automatically capture and send OpenAI API calls to [AnoSys](https://anosys.ai) for monitoring, analytics, and observability.

## Features

- **Automatic OpenAI Instrumentation** - Captures instrumented OpenAI API calls via OpenTelemetry
- **Streaming Support** - Detects and logs streaming responses
- **OpenTelemetry Semantic Conventions** - Follows Gen AI standards
- **Error Tracking** - Captures exceptions with full stack traces

## Installation

Requires Python 3.10 or later.

```bash
pip install anosys-sdk-openai
```

## Quick Start

```python
import os
from openai import OpenAI
from anosys_sdk_openai import AnosysOpenAILogger

os.environ["OPENAI_API_KEY"] = "your-openai-key"
os.environ["ANOSYS_API_KEY"] = "your-anosys-key"

# Initialize (do once at startup)
AnosysOpenAILogger()

# Use OpenAI normally - instrumented calls are logged
client = OpenAI()

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"}
    ]
)
print(response.choices[0].message.content)
```

## Streaming

Streaming is automatically detected and logged:

```python
stream = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Write a haiku"}],
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

## Custom Function Logging

You can also log custom functions using decorators from the core package:

```python
from anosys_sdk_core import anosys_logger

@anosys_logger(source="my_app")
def process_response(response):
    return response.choices[0].message.content
```

## What Data is Captured?

Following [OpenTelemetry Gen AI standards](https://opentelemetry.io/docs/specs/semconv/gen-ai/):

- `gen_ai.system` - Always "openai"
- `gen_ai.request.model` - Model requested
- `gen_ai.response.model` - Model that responded
- `gen_ai.request.temperature` - Temperature parameter
- `gen_ai.usage.input_tokens` - Input token count
- `gen_ai.usage.output_tokens` - Output token count
- Request/response messages
- Timestamps and duration
- Error details

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANOSYS_API_KEY` | Yes | Your AnoSys API key |
| `OPENAI_API_KEY` | Yes | Your OpenAI API key |

## License

Apache 2.0

## Content controls

See the [content-controls reference](../../../DATA_CONTROLS.md) for encryption coverage, default columns, redaction, and limitations. Encryption is opt-in and applies to selected string fields; it does not encrypt the complete record.
