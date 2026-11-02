# AnoSys SDK

Python and JavaScript integrations for [AnoSys](https://anosys.ai), the AI Operational Intelligence Platform.

Capture model calls, agent runs, tool activity, token usage, estimated cost, and application context. AnoSys connects these signals with evaluations, user behavior, and business outcomes to help teams investigate regressions, understand their impact, and verify fixes.

[Documentation](https://docs.anosys.ai) · [Console](https://console.anosys.ai) · [Integration options](https://console.anosys.ai/collect/integrationoptions) · [Support](mailto:support@anosys.ai)

## Integrations

| Integration | Python | JavaScript | Collection method |
| --- | --- | --- | --- |
| OpenAI API | [Guide](packages/python/openai/README.md) | [Guide](packages/js/openai/README.md) | OpenTelemetry instrumentation |
| OpenAI Agents SDK | [Guide](packages/python/openai_agents/README.md) | [Guide](packages/js/openai-agents/README.md) | Tracing processor |
| Anthropic API | [Guide](packages/python/anthropic/README.md) | [Guide](packages/js/anthropic/README.md) | Native Anthropic OpenTelemetry spans |
| Claude Agent SDK | [Guide](packages/python/claude_agents/README.md) | [Guide](packages/js/claude-agents/README.md) | Agent, tool, and subagent spans from the message stream |
| Claude Code | [Guide](packages/python/claude_code/README.md) | [Guide](packages/js/claude-code/README.md) | Stop hook and local transcripts |
| Codex CLI | [Guide](packages/python/codex/README.md) | [Guide](packages/js/codex/README.md) | Turn-complete notify callback and local rollout transcripts |
| Antigravity | [Development guide](ANTIGRAVITY.md) | [Development guide](ANTIGRAVITY.md) | Development branch; not released on npm or PyPI |

Antigravity is implemented on [moisisv/antigravity](https://github.com/Anosys-AI/anosys-sdk/tree/moisisv/antigravity), not on main. It captures agent activity, tool calls, commands, files, and duration. Token usage and cost are unavailable. See the [source installation instructions](ANTIGRAVITY.md).

## Published packages

Python packages require Python 3.10 or later. JavaScript packages declare Node.js 18 or later; use a supported Node.js release for deployment.

### Python

| Package | Version | Install |
| --- | --- | --- |
| [anosys-sdk-core](packages/python/core/) | 1.1.0 | `pip install anosys-sdk-core` |
| [anosys-sdk-openai](packages/python/openai/) | 1.0.14 | `pip install anosys-sdk-openai` |
| [anosys-sdk-openai-agents](packages/python/openai_agents/) | 1.0.13 | `pip install anosys-sdk-openai-agents` |
| [anosys-sdk-anthropic](packages/python/anthropic/) | 1.0.0 | `pip install anosys-sdk-anthropic` |
| [anosys-sdk-claude-agents](packages/python/claude_agents/) | 1.0.0 | `pip install anosys-sdk-claude-agents` |
| [anosys-claude-code](packages/python/claude_code/) | 0.2.9 | `pip install anosys-claude-code` |
| [anosys-codex](packages/python/codex/) | 0.1.0 | `pip install anosys-codex` |

### JavaScript

| Package | Version | Install |
| --- | --- | --- |
| [anosys-sdk-openai](packages/js/openai/) | 1.0.12 | `npm install anosys-sdk-openai openai` |
| [anosys-sdk-openai-agents](packages/js/openai-agents/) | 1.0.12 | `npm install anosys-sdk-openai-agents @openai/agents` |
| [anosys-sdk-anthropic](packages/js/anthropic/) | 1.0.0 | `npm install anosys-sdk-anthropic @anthropic-ai/sdk` |
| [anosys-sdk-claude-agents](packages/js/claude-agents/) | 1.0.0 | `npm install anosys-sdk-claude-agents @anthropic-ai/claude-agent-sdk` |
| [anosys-sdk-claude-code](packages/js/claude-code/) | 0.2.6 | `npx -y anosys-sdk-claude-code install` |
| [anosys-sdk-codex](packages/js/codex/) | 0.1.0 | `npm install -g anosys-sdk-codex` |

## Getting started

Create an AnoSys account and obtain a key from [integration options](https://console.anosys.ai/collect/integrationoptions). Use a telemetry endpoint for API and agent SDK instrumentation, and a **Claude Code & Codex CLI (CC)** endpoint for coding-tool hooks. Provider credentials are separate from the AnoSys ingestion key.

```bash
export ANOSYS_API_KEY="your-anosys-key"
export OPENAI_API_KEY="your-openai-key"       # OpenAI integrations
export ANTHROPIC_API_KEY="your-anthropic-key" # Anthropic integrations
```

The following examples use OPENAI_MODEL or ANTHROPIC_MODEL for a model available to your account. Set the variable for the provider you use.

### OpenAI

```python
import os
from openai import OpenAI
from anosys_sdk_openai import AnosysOpenAILogger

AnosysOpenAILogger()
client = OpenAI()
response = client.chat.completions.create(
    model=os.environ["OPENAI_MODEL"],
    messages=[{"role": "user", "content": "Hello"}],
)
```

```javascript
import OpenAI from 'openai';
import { AnosysOpenAILogger } from 'anosys-sdk-openai';

new AnosysOpenAILogger();
const client = new OpenAI();
const response = await client.chat.completions.create({
  model: process.env.OPENAI_MODEL,
  messages: [{ role: 'user', content: 'Hello' }],
});
```

### Anthropic

Initialize the logger before constructing clients. The supplied options helper carries the tracer provider and content-capture setting explicitly.

```python
import os
import anthropic
from anosys_sdk_anthropic import (
    AnosysAnthropicLogger,
    get_anthropic_open_telemetry_options,
)

AnosysAnthropicLogger(capture_content=True)
client = anthropic.Anthropic(
    open_telemetry=get_anthropic_open_telemetry_options(),
)
message = client.messages.create(
    model=os.environ["ANTHROPIC_MODEL"],
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}],
)
```

```javascript
import Anthropic from '@anthropic-ai/sdk';
import {
  AnosysAnthropicLogger,
  getAnthropicOpenTelemetryOptions,
} from 'anosys-sdk-anthropic';

new AnosysAnthropicLogger({ captureContent: true });
const client = new Anthropic({
  openTelemetry: getAnthropicOpenTelemetryOptions(),
});
const message = await client.messages.create({
  model: process.env.ANTHROPIC_MODEL,
  max_tokens: 1024,
  messages: [{ role: 'user', content: 'Hello' }],
});
```

For agent integrations, follow the package guides in the integration table. JavaScript Claude Agents requires wrapping query with wrapQuery; Python can instrument query and ClaudeSDKClient.

### Coding tools

Claude Code:

```bash
pip install anosys-claude-code
anosys-claude-code install

# Or use the JavaScript integration
npx -y anosys-sdk-claude-code install
```

Codex CLI:

```bash
pip install anosys-codex
anosys-codex install

# Or install the JavaScript CLI persistently
npm install -g anosys-sdk-codex
anosys-codex install
```

Choose one language implementation per tool to avoid duplicate collection. Read the [Python Codex setup note](packages/python/codex/README.md#notification-command-for-version-010) before using version 0.1.0: its notification command needs an explicit module invocation. Codex notify callbacks are separate from lifecycle hooks listed by /hooks. Restart Codex after changing its configuration.

## Content controls and encryption

Content capture is enabled by default in the Anthropic and Claude Agent SDK integrations. Set capture_content=False in Python or captureContent: false in JavaScript to omit conversation and tool content from those integrations. Coding-tool installers offer --redaction to replace supported content fields; this is field masking, not automatic detection of every kind of personal data.

Published SDKs support opt-in encryption of selected string fields before telemetry is sent:

```bash
export ANOSYS_ENCRYPTION_KEY="your-secret-passphrase"
# Optional: replaces the default field selection
export ANOSYS_ENCRYPTED_COLUMNS="llm_input,llm_output,cvs199"
```

The implementation uses SHA-256 key derivation, AES-256-CBC, a fixed zero IV, PKCS#7 padding, and Base64 ciphertext prefixed with enc:. It encrypts selected strings, not the complete record. Non-string values are skipped, and untargeted fields remain visible. This format is deterministic and does not authenticate ciphertext. Keep the passphrase outside source control and configure browser decryption separately.

See [content controls](DATA_CONTROLS.md) for coverage, default columns, environment configuration, and limitations. The unreleased Antigravity branch does not include this encryption implementation.

## Examples and references

| Workflow | OpenAI | Anthropic / Claude Agents |
| --- | --- | --- |
| Chat calls | [Notebook](examples/anosys_openai_chat_poc.ipynb) | [Notebook](examples/anosys_anthropic_chat_poc.ipynb) |
| Agent workflow | [Notebook](examples/anosys_openai_agentic_poc.ipynb) | [Notebook](examples/anosys_claude_agents_agentic_poc.ipynb) |
| Support copilot | [Notebook](examples/anosys_openai_support_copilot_demo.ipynb) | [Notebook](examples/anosys_anthropic_support_copilot_demo.ipynb) |
| Research pipeline | [Notebook](examples/anosys_openai_research_pipeline_demo.ipynb) | [Notebook](examples/anosys_claude_agents_research_pipeline_demo.ipynb) |

- [Telemetry variables](TELEMETRY_VARIABLES.md)
- [Claude Code variables](CLAUDE_CODE_VARIABLES.md)
- [Column mappings](MAPPINGS.md)
- [Core decorators and custom logging](packages/python/core/README.md)
- [Antigravity development status](ANTIGRAVITY.md)

## Development

```bash
make install-dev
make test
make lint
make build-py
```

The JavaScript packages ship source modules and do not require compilation. To inspect a distribution, run npm pack --dry-run from its package directory. CI covers Python 3.10, 3.11, and 3.12 and Node.js 18, 20, and 22. Provider-dependent notebooks require credentials and are not integration tests of a live model service.

## Releases

```bash
scripts/release.sh <component> <new-version>
```

| Component | Package | Registry |
| --- | --- | --- |
| core | anosys-sdk-core | PyPI |
| openai-py / openai-js | anosys-sdk-openai | PyPI / npm |
| openai-agents-py / openai-agents-js | anosys-sdk-openai-agents | PyPI / npm |
| anthropic-py / anthropic-js | anosys-sdk-anthropic | PyPI / npm |
| claude-agents-py / claude-agents-js | anosys-sdk-claude-agents | PyPI / npm |
| claude-code | anosys-claude-code | PyPI |
| claude-code-js | anosys-sdk-claude-code | npm |
| codex | anosys-codex | PyPI |
| codex-js | anosys-sdk-codex | npm |

The script updates the manifest and asks before committing, tagging, and pushing. Tags use <component>-v<version> and trigger the corresponding GitHub Actions workflow. Antigravity has no release component on main yet. Review package guides and this version table when publishing a release.

## License

[Apache License 2.0](LICENSE).
