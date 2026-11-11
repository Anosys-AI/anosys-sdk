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
| Antigravity | [Guide](packages/python/antigravity/README.md) | [Guide](packages/js/antigravity/README.md) | PreInvocation and Stop hooks with local transcripts |

Antigravity captures agent activity, tool calls, commands, files, and duration. Its hook inputs and local transcripts do not expose token usage or cost. See the [Antigravity setup guide](ANTIGRAVITY.md).

## Published packages

Python packages require Python 3.10 or later. JavaScript packages declare Node.js 18 or later; use a supported Node.js release for deployment.

### Python

| Package | Version | Install |
| --- | --- | --- |
| [anosys-sdk-core](packages/python/core/) | 2.0.0 | `pip install anosys-sdk-core` |
| [anosys-sdk-openai](packages/python/openai/) | 1.1.0 | `pip install anosys-sdk-openai` |
| [anosys-sdk-openai-agents](packages/python/openai_agents/) | 1.1.0 | `pip install anosys-sdk-openai-agents` |
| [anosys-sdk-anthropic](packages/python/anthropic/) | 1.1.0 | `pip install anosys-sdk-anthropic` |
| [anosys-sdk-claude-agents](packages/python/claude_agents/) | 1.1.0 | `pip install anosys-sdk-claude-agents` |
| [anosys-claude-code](packages/python/claude_code/) | 0.3.0 | `pip install anosys-claude-code` |
| [anosys-codex](packages/python/codex/) | 0.2.0 | `pip install anosys-codex` |
| [anosys-antigravity](packages/python/antigravity/) | 0.2.0 | `pip install anosys-antigravity` |

### JavaScript

| Package | Version | Install |
| --- | --- | --- |
| [anosys-sdk-core](packages/js/core/) | 2.0.0 | `npm install anosys-sdk-core` |
| [anosys-sdk-openai](packages/js/openai/) | 1.1.0 | `npm install anosys-sdk-openai openai` |
| [anosys-sdk-openai-agents](packages/js/openai-agents/) | 1.1.0 | `npm install anosys-sdk-openai-agents @openai/agents` |
| [anosys-sdk-anthropic](packages/js/anthropic/) | 1.1.0 | `npm install anosys-sdk-anthropic @anthropic-ai/sdk` |
| [anosys-sdk-claude-agents](packages/js/claude-agents/) | 1.1.0 | `npm install anosys-sdk-claude-agents @anthropic-ai/claude-agent-sdk` |
| [anosys-sdk-claude-code](packages/js/claude-code/) | 0.3.0 | `npx -y anosys-sdk-claude-code install` |
| [anosys-sdk-codex](packages/js/codex/) | 0.2.0 | `npm install -g anosys-sdk-codex` |
| [anosys-sdk-antigravity](packages/js/antigravity/) | 0.2.0 | `npm install -g anosys-sdk-antigravity` |

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

Antigravity:

```bash
pip install anosys-antigravity
anosys-antigravity install

# Or use the JavaScript integration
npm install -g anosys-sdk-antigravity
anosys-antigravity install
```

Choose one language implementation per tool to avoid duplicate collection. Codex notify callbacks are separate from lifecycle hooks listed by /hooks. Restart each coding tool after changing its configuration.

## Content controls and encryption

Every package collects at one of three levels: `off`, `metadata` or `full`.

- **Application SDKs** (OpenAI, OpenAI Agents, Anthropic, Claude Agent SDK, decorators) default to `full`. Use `capture_content=False` in Python, `captureContent: false` in JavaScript, or `ANOSYS_COLLECTION_LEVEL=metadata` to send metadata only.
- **Coding-tool hooks** (Claude Code, Codex, Antigravity) default to `metadata`. Full content requires accepting the [data collection policy](PRIVACY.md) with `<tool> privacy full`, and `<tool> privacy off` stops collection.
- `ANOSYS_DISABLE=1` turns everything off, and a project `.anosys` file with `level=metadata` or `level=off` lowers the level for that folder. Nothing can raise a level the user lowered.

Each record says which level applied in `cvs198`. Every package keeps requests under 10 MB (`ANOSYS_MAX_BATCH_BYTES`).

All integrations can encrypt content before it is sent:

```bash
export ANOSYS_ENCRYPTION_KEY="your-secret-passphrase"
export ANOSYS_ENCRYPTION_SALT="your-workspace-salt"
# Optional: replaces the default field selection
export ANOSYS_ENCRYPTED_COLUMNS="llm_input,llm_output,cvs199"
```

With a key set, every column outside the metadata allowlist is encrypted; ids, timing, models and token counts stay readable. The `enc2` format uses PBKDF2-SHA256 key derivation with a workspace salt and deterministic AES-256-GCM, so dashboards can still group and join on encrypted values. Keep the passphrase outside source control.

See [content controls](DATA_CONTROLS.md) for coverage, default columns, size limits and the format, and [PRIVACY.md](PRIVACY.md) for what the hooks collect.

## Examples and references

| Workflow | OpenAI | Anthropic / Claude Agents |
| --- | --- | --- |
| Chat calls | [Notebook](examples/anosys_openai_chat_poc.ipynb) | [Notebook](examples/anosys_anthropic_chat_poc.ipynb) |
| Agent workflow | [Notebook](examples/anosys_openai_agentic_poc.ipynb) | [Notebook](examples/anosys_claude_agents_agentic_poc.ipynb) |
| Support copilot | [Notebook](examples/anosys_openai_support_copilot_demo.ipynb) | [Notebook](examples/anosys_anthropic_support_copilot_demo.ipynb) |
| Research pipeline | [Notebook](examples/anosys_openai_research_pipeline_demo.ipynb) | [Notebook](examples/anosys_claude_agents_research_pipeline_demo.ipynb) |

Other examples:

- [Decorators](examples/anosys_core_decorators_poc.ipynb): trace your own functions with `@anosys_logger`, including async functions, generators and errors.
- [LangChain](examples/anosys_langchain_agentic_poc.ipynb): a LangChain tool-calling loop on OpenAI, traced through `AnosysOpenAILogger`.
- [OpenRouter](examples/anosys_openrouter_agentic_poc.ipynb): the same loop against models served by OpenRouter.

References:

- [Release notes](RELEASE_NOTES.md)
- [Telemetry variables](TELEMETRY_VARIABLES.md)
- [Claude Code variables](CLAUDE_CODE_VARIABLES.md)
- [Column mappings](MAPPINGS.md)
- [Core decorators and custom logging](packages/python/core/README.md)
- [Antigravity setup](ANTIGRAVITY.md)
- [Antigravity variables](ANTIGRAVITY_VARIABLES.md)

## Development

```bash
make install-dev
make test
make healthcheck   # before every release
```

`make healthcheck` runs the [release health check](testcases/README.md): content leaks at every level, the privacy settings, the real hooks and SDK clients end to end against a local fake server, and package contents. The JavaScript packages ship source modules and do not require compilation. To inspect a distribution, run `npm pack --dry-run` from its package directory. CI covers Python 3.10, 3.11, and 3.12 and Node.js 18, 20, and 22. The example notebooks need provider and AnoSys keys.

## Releases

```bash
scripts/release.sh <component> <new-version>
```

| Component | Package | Registry |
| --- | --- | --- |
| core / core-js | anosys-sdk-core | PyPI / npm |
| openai-py / openai-js | anosys-sdk-openai | PyPI / npm |
| openai-agents-py / openai-agents-js | anosys-sdk-openai-agents | PyPI / npm |
| anthropic-py / anthropic-js | anosys-sdk-anthropic | PyPI / npm |
| claude-agents-py / claude-agents-js | anosys-sdk-claude-agents | PyPI / npm |
| claude-code | anosys-claude-code | PyPI |
| claude-code-js | anosys-sdk-claude-code | npm |
| codex | anosys-codex | PyPI |
| codex-js | anosys-sdk-codex | npm |
| antigravity | anosys-antigravity | PyPI |
| antigravity-js | anosys-sdk-antigravity | npm |

The script updates the manifest and asks before committing, tagging and pushing. Tags use `<component>-v<version>` and trigger the matching GitHub Actions workflow. Release `core` and `core-js` first, since every other package depends on them, and update [RELEASE_NOTES.md](RELEASE_NOTES.md) and the version table above.

## License

[Apache License 2.0](LICENSE).
