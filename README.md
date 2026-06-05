# AnoSys SDK

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![CI](https://github.com/anosys-ai/anosys-sdk/actions/workflows/ci.yml/badge.svg)](https://github.com/anosys-ai/anosys-sdk/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Node.js](https://img.shields.io/badge/node-%E2%89%A518-green.svg)](https://nodejs.org/)

Official SDKs for integrating with [AnoSys](https://anosys.ai) — AI observability, monitoring, and analytics platform.

Add a few lines of code and every LLM call, agent run, and Claude Code session is automatically captured and sent to your AnoSys workspace.

---

## Packages

### Python

| Package | Version | Description | Install |
|---------|---------|-------------|---------|
| [`anosys-sdk-core`](./packages/python/core/) | 1.0.13 | Shared core — config, HTTP client, decorators, data models | `pip install anosys-sdk-core` |
| [`anosys-sdk-openai`](./packages/python/openai/) | 1.0.13 | OpenAI SDK instrumentation via OpenTelemetry | `pip install anosys-sdk-openai` |
| [`anosys-sdk-openai-agents`](./packages/python/openai_agents/) | 1.0.12 | OpenAI Agents SDK tracing (TracingProcessor) | `pip install anosys-sdk-openai-agents` |
| [`anosys-claude-code`](./packages/python/claude_code/) | 0.2.8 | Claude Code observability hook & CLI | `pip install anosys-claude-code` |

### JavaScript / Node.js

| Package | Version | Description | Install |
|---------|---------|-------------|---------|
| [`anosys-sdk-openai`](./packages/js/openai/) | 1.0.11 | OpenAI SDK instrumentation via OpenTelemetry | `npm install anosys-sdk-openai` |
| [`anosys-sdk-openai-agents`](./packages/js/openai-agents/) | 1.0.11 | OpenAI Agents SDK tracing (`addTracingProcessor`) | `npm install anosys-sdk-openai-agents` |
| [`anosys-sdk-claude-code`](./packages/js/claude-code/) | 0.2.5 | Claude Code observability hook & CLI | `npx anosys-sdk-claude-code install` |

---

## Quick Start

### Prerequisites

1. Sign up at [anosys.ai](https://anosys.ai) and obtain your **AnoSys API Key** from the [integration options page](https://console.anosys.ai/collect/integrationoptions).
2. Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

```ini
# Required
ANOSYS_API_KEY=your_anosys_api_key_here

# Required for OpenAI integrations
OPENAI_API_KEY=your_openai_api_key_here

# Optional overrides
# ANOSYS_API_URL=https://www.anosys.ai
# ANOSYS_RESOLVER_URL=https://console.anosys.ai/api/resolveapikeys
```

---

### OpenAI — Python

```python
import os
from openai import OpenAI
from anosys_sdk_openai import AnosysOpenAILogger

os.environ["OPENAI_API_KEY"] = "your-openai-key"
os.environ["ANOSYS_API_KEY"] = "your-anosys-key"

# Initialize once at startup — all subsequent calls are logged automatically
AnosysOpenAILogger()

client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello!"}]
)
print(response.choices[0].message.content)
```

### OpenAI — JavaScript

```js
import { AnosysOpenAILogger } from 'anosys-sdk-openai';
import OpenAI from 'openai';

// Initialize once — instruments all subsequent OpenAI calls automatically
new AnosysOpenAILogger();

const client = new OpenAI();
const response = await client.chat.completions.create({
  model: 'gpt-4o',
  messages: [{ role: 'user', content: 'Hello' }],
});
```

---

### OpenAI Agents — Python

```python
from agents import Agent, Runner, set_tracing_processor
from anosys_sdk_openai_agents import AnosysOpenAIAgentsLogger

set_tracing_processor(AnosysOpenAIAgentsLogger())

agent = Agent(name="Assistant", instructions="You are helpful.")
result = Runner.run_sync(agent, "Hello!")
print(result.final_output)
```

### OpenAI Agents — JavaScript

```js
import { AnosysOpenAIAgentsLogger } from 'anosys-sdk-openai-agents';
import { Agent, run, addTracingProcessor } from '@openai/agents';

const logger = new AnosysOpenAIAgentsLogger();
addTracingProcessor(logger);

const agent = new Agent({ name: 'my-agent', instructions: 'You are helpful.' });
const result = await run(agent, 'Hello');
```

---

### Claude Code — Python

Install the package and run the setup wizard:

```bash
pip install anosys-claude-code
anosys-claude-code install
```

Or install headlessly:

```bash
anosys-claude-code install \
  --api-key "your_logs_api_key" \
  --otel-key "your_otel_api_key" \
  --redaction
```

CLI commands: `install` · `uninstall` · `status` · `run`

### Claude Code — JavaScript

```bash
npx anosys-sdk-claude-code install
```

Or install headlessly:

```bash
npx anosys-sdk-claude-code install \
  --api-key "your_logs_api_key" \
  --otel-key "your_otel_api_key" \
  --redaction
```

CLI commands: `install` · `uninstall` · `status` · `run`

**How it works:** When installed, both Python and JS packages register a `Stop` hook in `~/.claude/settings.json`. When a Claude Code session ends, the hook scans local transcripts (`~/.claude/projects/`), incrementally maps new messages and subagent events, calculates pricing, applies optional content redaction, and batches results to your AnoSys workspace.

---

### Custom Function Logging

Use the core decorator to log any function — works with both sync and async:

#### Python

```python
from anosys_sdk_core import anosys_logger, anosys_raw_logger

@anosys_logger(source="my_app")
def my_function(data):
    return process(data)

@anosys_logger(source="my_app.async")
async def my_async_function(data):
    return await async_process(data)

# Log arbitrary data directly
anosys_raw_logger({"event": "custom_event", "data": {"key": "value"}})
```

#### JavaScript

```js
import { anosysLogger, anosysRawLogger } from 'anosys-sdk-openai';

const myFunction = anosysLogger('my_app.pipeline')(async (input) => {
  // your logic
  return result;
});

// Log arbitrary data directly
await anosysRawLogger({ event: 'user_action', user_id: 'u123', value: 42 });
```

---

### User Context

Associate traces with user sessions for richer analytics:

#### Python

```python
from anosys_sdk_openai_agents import AnosysOpenAIAgentsLogger

def get_user_context():
    return {"session_id": "user-123", "token": "auth-token"}

processor = AnosysOpenAIAgentsLogger(get_user_context=get_user_context)
```

#### JavaScript

```js
new AnosysOpenAILogger({
  getUserContext: () => ({ session_id: req.sessionId, token: req.token }),
});
```

---

## Repository Structure

```
anosys-sdk/
├── packages/
│   ├── python/
│   │   ├── core/               # anosys-sdk-core
│   │   ├── openai/             # anosys-sdk-openai
│   │   ├── openai_agents/      # anosys-sdk-openai-agents
│   │   └── claude_code/        # anosys-claude-code
│   └── js/
│       ├── openai/             # anosys-sdk-openai (npm)
│       ├── openai-agents/      # anosys-sdk-openai-agents (npm)
│       └── claude-code/        # anosys-sdk-claude-code (npm)
├── examples/                   # Jupyter notebook demos
├── scripts/
│   └── release.sh              # Per-package release script
├── MAPPINGS.md                 # CVS variable mapping reference
├── Makefile                    # Build, test, lint shortcuts
└── .github/workflows/
    ├── ci.yml                  # CI: Python 3.10–3.12, Node 18/20/22
    ├── release-python.yml      # Auto-publish Python packages to PyPI
    ├── release-js.yml          # Auto-publish JS packages to npm
    └── claudecode-install-test.yml
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANOSYS_API_KEY` | Yes | Your AnoSys API key ([get one here](https://console.anosys.ai/collect/integrationoptions)) |
| `OPENAI_API_KEY` | Yes* | Required for OpenAI / OpenAI Agents packages |
| `ANOSYS_API_URL` | No | Override the logging endpoint (default: `https://www.anosys.ai`) |
| `ANOSYS_RESOLVER_URL` | No | Override the API key resolver endpoint |
| `ANOSYS_LOG_LEVEL` | No | JS only: `debug` / `info` / `warn` / `error` / `silent` (default: `warn`) |

---

## Development

### Setup

```bash
# Install all Python packages in editable mode + JS workspaces
make install

# Install with dev dependencies (pytest, ruff, etc.)
make install-dev
```

### Testing

```bash
# Run all tests (Python + JS)
make test

# Python only
make test-py

# JavaScript only
make test-js
```

CI runs on every push/PR to `main` across **Python 3.10 / 3.11 / 3.12** and **Node.js 18 / 20 / 22**.

### Linting & Formatting

```bash
# Lint Python with Ruff
make lint

# Auto-format Python
make format-py
```

### Building

```bash
# Build all Python packages
make build-py

# Build all JS packages
make build-js

# Remove all build artifacts
make clean
```

---

## Releasing

Releases are per-package using the included release script:

```bash
scripts/release.sh <component> <version>
```

**Components:**

| Component | Package | Registry |
|-----------|---------|----------|
| `core` | `anosys-sdk-core` | PyPI |
| `openai-py` | `anosys-sdk-openai` | PyPI |
| `openai-agents-py` | `anosys-sdk-openai-agents` | PyPI |
| `claude-code` | `anosys-claude-code` | PyPI |
| `openai-js` | `anosys-sdk-openai` | npm |
| `openai-agents-js` | `anosys-sdk-openai-agents` | npm |
| `claude-code-js` | `anosys-sdk-claude-code` | npm |

The script bumps the version, commits, tags as `<component>-v<version>`, and pushes. The corresponding GitHub Actions workflow builds and publishes the package automatically.

**Example:**

```bash
scripts/release.sh openai-js 1.0.12
```

---

## Examples

The [`examples/`](./examples/) directory contains Jupyter notebooks demonstrating end-to-end integrations:

- **`anosys_openai_chat_poc.ipynb`** — Basic OpenAI chat completions logging
- **`anosys_openai_agentic_poc.ipynb`** — Multi-agent workflow with full trace capture

---

## Documentation

- **SDK Docs**: [docs.anosys.ai](https://docs.anosys.ai)
- **AnoSys Console**: [console.anosys.ai](https://console.anosys.ai)
- **CVS Variable Mappings**: [MAPPINGS.md](./MAPPINGS.md) — full reference for how SDK fields map to AnoSys platform variables

---

## License

Apache 2.0 — see [LICENSE](./LICENSE).
<img src="https://api.anosys.ai/trafficpixel/925fb3f78b04d5b9d5aded56b44410c9/a/ea8a7985c8f3/anosys.gif?cvs198=https://github.com/Anosys-AI/anosys-sdk" width="1" height="1" alt=""/>
