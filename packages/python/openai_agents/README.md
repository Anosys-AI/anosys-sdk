<p align="center">
  <a href="https://anosys.ai">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/anosys-ai/anosys-sdk/main/assets/anosys-new-white-darkmode.svg">
      <img src="https://raw.githubusercontent.com/anosys-ai/anosys-sdk/main/assets/anosys-new-black-lightmode.svg" alt="Anosys.ai" width="240">
    </picture>
  </a>
</p>

# AnoSys SDK for OpenAI Agents

Automatically capture and send OpenAI Agents SDK traces to [AnoSys](https://anosys.ai) for monitoring, analytics, and observability.

## Features

- **Automatic Agent Tracing** - Captures all agent runs, tool calls, and handoffs
- **TracingProcessor Integration** - Native integration with OpenAI Agents SDK
- **Structured Span Data** - Captures agent, function, guardrail, and generation spans
- **User Context Support** - Associate traces with user sessions

## Installation

Requires Python 3.10 or later.

```bash
pip install anosys-sdk-openai-agents
```

## Quick Start

```python
import os
from agents import Agent, Runner, add_trace_processor
from anosys_sdk_openai_agents import AnosysOpenAIAgentsLogger

os.environ["OPENAI_API_KEY"] = "your-openai-key"
os.environ["ANOSYS_API_KEY"] = "your-anosys-key"

# Set up the tracing processor
add_trace_processor(AnosysOpenAIAgentsLogger())

# Create and run an agent
agent = Agent(
    name="Assistant",
    instructions="You are a helpful assistant."
)

result = Runner.run_sync(agent, "Hello!")
print(result.final_output)
```

## User Context

Associate traces with user sessions:

```python
def get_user_context():
    return {
        "session_id": "user-123",
        "token": "auth-token"
    }

processor = AnosysOpenAIAgentsLogger(get_user_context=get_user_context)
add_trace_processor(processor)
```

## Span Types Captured

- **agent** - Agent execution spans
- **function** - Tool/function calls
- **generation** - LLM generation calls
- **guardrail** - Guardrail checks
- **handoff** - Agent handoffs
- **response** - Response spans
- **custom** - Custom spans

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANOSYS_API_KEY` | Yes | Your AnoSys API key |
| `OPENAI_API_KEY` | Yes | Your OpenAI API key |

## License
Apache 2.0

## Content controls

See the [content-controls reference](../../../DATA_CONTROLS.md) for encryption coverage, default columns, size limits, and limitations. Encryption is opt-in and applies to selected string fields; it does not encrypt the complete record.

Collection follows one level for every AnoSys SDK: `ANOSYS_COLLECTION_LEVEL=full` (default), `metadata` (no prompts, completions or tool data) or `off`, a project `.anosys` file can only lower it, and `ANOSYS_DISABLE=1` stops all sending. Without an API key nothing is sent. Telemetry is sent in the background and never delays your calls. See the [data-collection policy](../../../PRIVACY.md).
