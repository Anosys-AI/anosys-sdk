# Anosys SDK

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)

SDKs for integrating with [AnoSys](https://anosys.ai) - AI observability and monitoring platform.

## Packages

### Python

| Package | Description | Install |
|---------|-------------|---------|
| [`anosys-sdk-core`](./packages/python/core/) | Shared core utilities | `pip install anosys-sdk-core` |
| [`anosys-sdk-openai`](./packages/python/openai/) | OpenAI SDK instrumentation | `pip install anosys-sdk-openai` |
| [`anosys-sdk-openai-agents`](./packages/python/openai_agents/) | OpenAI Agents SDK instrumentation | `pip install anosys-sdk-openai-agents` |
| [`anosys-claude-code`](./packages/python/claude_code/) | Claude Code observability hook | `pip install anosys-claude-code` |

### JavaScript

| Package | Description | Install |
|---------|-------------|---------|
| [`anosys-sdk-openai`](./packages/js/openai/) | OpenAI SDK instrumentation | `npm install anosys-sdk-openai` |
| [`anosys-sdk-openai-agents`](./packages/js/openai-agents/) | OpenAI Agents SDK instrumentation | `npm install anosys-sdk-openai-agents` |
| [`anosys-sdk-claude-code`](./packages/js/claude-code/) | Claude Code observability hook | `npm install anosys-sdk-claude-code` |

## Quick Start

### OpenAI Integration

```python
import os
from openai import OpenAI
from anosys_sdk_openai import AnosysOpenAILogger

os.environ["OPENAI_API_KEY"] = "your-openai-key"
os.environ["ANOSYS_API_KEY"] = "your-anosys-key"

# Initialize logging (do once)
AnosysOpenAILogger()

# Use OpenAI normally - calls are automatically logged
client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

### OpenAI Agents Integration

```python
from agents import Agent, Runner, set_tracing_processor
from anosys_sdk_openai_agents import AnosysOpenAIAgentsLogger

set_tracing_processor(AnosysOpenAIAgentsLogger())

agent = Agent(name="Assistant", instructions="You are helpful.")
result = Runner.run_sync(agent, "Hello!")
```

### Custom Function Logging

```python
from anosys_sdk_core import anosys_logger

@anosys_logger(source="my_app")
def my_function(data):
    return process(data)
```

## Development

```bash
# Install all packages in dev mode
make install

# Run tests
make test

# Build packages
make build
```

## License

Apache 2.0 License - see [LICENSE](./LICENSE)

