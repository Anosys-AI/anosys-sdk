# AnoSys SDK for OpenAI Agents

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)

Automatically capture and send OpenAI Agents SDK traces to [AnoSys](https://anosys.ai) for monitoring, analytics, and observability.

## Features

✨ **Automatic Agent Tracing** - Captures all agent runs, tool calls, and handoffs  
✨ **TracingProcessor Integration** - Native integration with OpenAI Agents SDK  
✨ **Structured Span Data** - Captures agent, function, guardrail, and generation spans  
✨ **User Context Support** - Associate traces with user sessions  

## Installation

```bash
pip install anosys-sdk-openai-agents
```

## Quick Start

```python
import os
from agents import Agent, Runner, set_tracing_processor
from anosys_sdk_openai_agents import AnosysOpenAIAgentsLogger

os.environ["OPENAI_API_KEY"] = "your-openai-key"
os.environ["ANOSYS_API_KEY"] = "your-anosys-key"

# Set up the tracing processor
set_tracing_processor(AnosysOpenAIAgentsLogger())

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
set_tracing_processor(processor)
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
