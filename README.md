<p align="center">
  <a href="https://anosys.ai">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="assets/anosys-new-white-darkmode.svg">
      <img src="assets/anosys-new-black-lightmode.svg" alt="Anosys.ai" width="360">
    </picture>
  </a>
</p>

# Anosys.ai SDK

Python and JavaScript integrations for [Anosys.ai](https://anosys.ai), the AI Operational Intelligence Platform. Add two lines to your app and see every model call, agent run and tool call, with token usage and cost, in one place.

[Documentation](https://docs.anosys.ai) · [Console](https://console.anosys.ai) · [Get an API key](https://console.anosys.ai/collect/integrationoptions) · [Release notes](RELEASE_NOTES.md) · [Support](mailto:support@anosys.ai)

## Quickstart

**1. Get an API key** from [Integration options](https://console.anosys.ai/collect/integrationoptions) in the Anosys.ai Console. Use a **Telemetry** key for your applications and a **Claude Code & Codex CLI** key for coding tools.

**2. Install and add the logger** before you create your client. Python 3.10+:

```bash
pip install anosys-sdk-openai openai
export ANOSYS_API_KEY="your-anosys-key"
```

```python
from openai import OpenAI
from anosys_sdk_openai import AnosysOpenAILogger

AnosysOpenAILogger()  # every OpenAI call from here on is traced
client = OpenAI()
client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello"}],
)
```

Node.js 18+:

```bash
npm install anosys-sdk-openai openai
```

```javascript
import OpenAI from 'openai';
import { AnosysOpenAILogger } from 'anosys-sdk-openai';

new AnosysOpenAILogger(); // every OpenAI call from here on is traced
const client = new OpenAI();
await client.chat.completions.create({
  model: 'gpt-4o-mini',
  messages: [{ role: 'user', content: 'Hello' }],
});
```

**3. Open the [Console](https://console.anosys.ai)** to see the call, its tokens and its cost.

Using Anthropic, an agent framework or a coding tool? Pick your integration below.

## Integrations

| Integration | Python | JavaScript | Example Use Cases | Sample Notebooks |
| --- | --- | --- | --- | --- |
| <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/openai-dark.svg"><img src="assets/logos/openai-light.svg" width="16" height="16" alt=""></picture> OpenAI API | [Guide](packages/python/openai/README.md) | [Guide](packages/js/openai/README.md) | <img src="assets/icons/pulse.svg" width="14" height="14" alt=""> Latency and errors<br><img src="assets/icons/graph.svg" width="14" height="14" alt=""> Tokens and cost per request<br><img src="assets/icons/bug.svg" width="14" height="14" alt=""> Debugging bad answers | [Chat](examples/anosys_openai_chat_poc.ipynb), [Support copilot](examples/anosys_openai_support_copilot_demo.ipynb) |
| <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/openai-dark.svg"><img src="assets/logos/openai-light.svg" width="16" height="16" alt=""></picture> OpenAI Agents SDK | [Guide](packages/python/openai_agents/README.md) | [Guide](packages/js/openai-agents/README.md) | <img src="assets/icons/workflow.svg" width="14" height="14" alt=""> Agent runs and delegation<br><img src="assets/icons/tools.svg" width="14" height="14" alt=""> Tool calls<br><img src="assets/icons/search.svg" width="14" height="14" alt=""> Finding the step that failed | [Agents](examples/anosys_openai_agentic_poc.ipynb), [Research pipeline](examples/anosys_openai_research_pipeline_demo.ipynb) |
| <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/anthropic-dark.svg"><img src="assets/logos/anthropic-light.svg" width="16" height="16" alt=""></picture> Anthropic API | [Guide](packages/python/anthropic/README.md) | [Guide](packages/js/anthropic/README.md) | <img src="assets/icons/pulse.svg" width="14" height="14" alt=""> Latency and errors<br><img src="assets/icons/graph.svg" width="14" height="14" alt=""> Tokens and cost per request<br><img src="assets/icons/bug.svg" width="14" height="14" alt=""> Debugging bad answers | [Chat](examples/anosys_anthropic_chat_poc.ipynb), [Support copilot](examples/anosys_anthropic_support_copilot_demo.ipynb) |
| <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/claude-dark.svg"><img src="assets/logos/claude-light.svg" width="16" height="16" alt=""></picture> Claude Agent SDK | [Guide](packages/python/claude_agents/README.md) | [Guide](packages/js/claude-agents/README.md) | <img src="assets/icons/workflow.svg" width="14" height="14" alt=""> Agent runs and delegation<br><img src="assets/icons/tools.svg" width="14" height="14" alt=""> Tool calls<br><img src="assets/icons/search.svg" width="14" height="14" alt=""> Finding the step that failed | [Agents](examples/anosys_claude_agents_agentic_poc.ipynb), [Research pipeline](examples/anosys_claude_agents_research_pipeline_demo.ipynb) |
| <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/claude-dark.svg"><img src="assets/logos/claude-light.svg" width="16" height="16" alt=""></picture> Claude Code | [Guide](packages/python/claude_code/README.md) | [Guide](packages/js/claude-code/README.md) | <img src="assets/icons/graph.svg" width="14" height="14" alt=""> Token and cost tracking and optimization<br><img src="assets/icons/person.svg" width="14" height="14" alt=""> Usage per developer, project and session<br><img src="assets/icons/search.svg" width="14" height="14" alt=""> Expensive sessions and models | — |
| <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/openai-dark.svg"><img src="assets/logos/openai-light.svg" width="16" height="16" alt=""></picture> Codex CLI | [Guide](packages/python/codex/README.md) | [Guide](packages/js/codex/README.md) | <img src="assets/icons/graph.svg" width="14" height="14" alt=""> Token and cost tracking and optimization<br><img src="assets/icons/person.svg" width="14" height="14" alt=""> Usage per developer, project and session<br><img src="assets/icons/search.svg" width="14" height="14" alt=""> Expensive sessions and models | — |
| <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/google-dark.svg"><img src="assets/logos/google-light.svg" width="16" height="16" alt=""></picture> Antigravity | [Guide](packages/python/antigravity/README.md) | [Guide](packages/js/antigravity/README.md) | <img src="assets/icons/workflow.svg" width="14" height="14" alt=""> Agent activity<br><img src="assets/icons/terminal.svg" width="14" height="14" alt=""> Tool calls and commands<br><img src="assets/icons/clock.svg" width="14" height="14" alt=""> Session time | — |

More notebooks: [decorators](examples/anosys_core_decorators_poc.ipynb) for your own functions, [LangChain](examples/anosys_langchain_agentic_poc.ipynb) and [OpenRouter](examples/anosys_openrouter_agentic_poc.ipynb). They run in Google Colab or locally.

### Anthropic

```bash
pip install anosys-sdk-anthropic anthropic        # or: npm install anosys-sdk-anthropic @anthropic-ai/sdk
```

```python
import anthropic
from anosys_sdk_anthropic import AnosysAnthropicLogger

AnosysAnthropicLogger()  # before creating the client
client = anthropic.Anthropic()
client.messages.create(
    model="claude-sonnet-5-5",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}],
)
```

If you pass your own `open_telemetry` option to the client, build it with `get_anthropic_open_telemetry_options()` so tracing keeps working; see the [Anthropic guide](packages/python/anthropic/README.md).

### Agent frameworks

Follow the guide for the [OpenAI Agents SDK](packages/python/openai_agents/README.md) or the [Claude Agent SDK](packages/python/claude_agents/README.md). In JavaScript, Claude Agent SDK calls are traced by wrapping `query` with `wrapQuery`.

### Coding tools

Each tool has one install command, which asks for your key and sets up the hook. Restart the tool afterwards.

Claude Code:
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

Use either the Python or the JavaScript version of a tool, not both, or every session is recorded twice. Antigravity has a few extra steps: see the [Antigravity setup guide](ANTIGRAVITY.md).

## Privacy and data controls

- **Applications** send prompts and responses by default. Use `capture_content=False` (Python), `captureContent: false` (JavaScript) or `ANOSYS_COLLECTION_LEVEL=metadata` to send only ids, timing, models and token counts.
- **Coding tools** send metadata only until each user runs `<tool> privacy full` and accepts the [data collection policy](PRIVACY.md). `<tool> privacy off` stops collection.
- **Anyone can turn collection down:** `ANOSYS_DISABLE=1` turns it off, and a `.anosys` file with `level=metadata` or `level=off` lowers it for a project.
- **Encryption:** set `ANOSYS_ENCRYPTION_KEY` and `ANOSYS_ENCRYPTION_SALT` (shown in the Console) and every content field is encrypted before it leaves your machine. Keep the passphrase out of source control.

Details: [content controls and encryption](DATA_CONTROLS.md). Column reference: [telemetry variables](TELEMETRY_VARIABLES.md), [Claude Code variables](CLAUDE_CODE_VARIABLES.md), [Antigravity variables](ANTIGRAVITY_VARIABLES.md), [column mappings](MAPPINGS.md).

## Troubleshooting

- **Nothing shows up.** Check that `ANOSYS_API_KEY` is set in the process that runs your app, and that the logger is created before the client. Without a valid key the SDK logs `telemetry is disabled` and sends nothing.
- **Coding tool data is missing.** Run `<tool> doctor`, for example `anosys-claude-code doctor`, to see the active hook, the collection level and the local files. Restart the tool after installing.
- **No prompts in coding tool data.** That is the default; run `<tool> privacy full` to include them.
- **Still stuck?** Email [support@anosys.ai](mailto:support@anosys.ai).

## Packages

<details>
<summary>All Python and JavaScript packages</summary>

### Python (3.10 or later)

| Package | Version | Install |
| --- | --- | --- |
| <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/anosys-dark.svg"><img src="assets/logos/anosys-light.svg" width="16" height="16" alt=""></picture> [anosys-sdk-core](packages/python/core/) | 2.0.0 | `pip install anosys-sdk-core` |
| <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/openai-dark.svg"><img src="assets/logos/openai-light.svg" width="16" height="16" alt=""></picture> [anosys-sdk-openai](packages/python/openai/) | 1.1.0 | `pip install anosys-sdk-openai` |
| <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/openai-dark.svg"><img src="assets/logos/openai-light.svg" width="16" height="16" alt=""></picture> [anosys-sdk-openai-agents](packages/python/openai_agents/) | 1.1.0 | `pip install anosys-sdk-openai-agents` |
| <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/anthropic-dark.svg"><img src="assets/logos/anthropic-light.svg" width="16" height="16" alt=""></picture> [anosys-sdk-anthropic](packages/python/anthropic/) | 1.1.0 | `pip install anosys-sdk-anthropic` |
| <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/claude-dark.svg"><img src="assets/logos/claude-light.svg" width="16" height="16" alt=""></picture> [anosys-sdk-claude-agents](packages/python/claude_agents/) | 1.1.0 | `pip install anosys-sdk-claude-agents` |
| <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/claude-dark.svg"><img src="assets/logos/claude-light.svg" width="16" height="16" alt=""></picture> [anosys-claude-code](packages/python/claude_code/) | 0.3.0 | `pip install anosys-claude-code` |
| <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/openai-dark.svg"><img src="assets/logos/openai-light.svg" width="16" height="16" alt=""></picture> [anosys-codex](packages/python/codex/) | 0.2.0 | `pip install anosys-codex` |
| <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/google-dark.svg"><img src="assets/logos/google-light.svg" width="16" height="16" alt=""></picture> [anosys-antigravity](packages/python/antigravity/) | 0.2.0 | `pip install anosys-antigravity` |

### JavaScript (Node.js 18 or later)

| Package | Version | Install |
| --- | --- | --- |
| <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/anosys-dark.svg"><img src="assets/logos/anosys-light.svg" width="16" height="16" alt=""></picture> [anosys-sdk-core](packages/js/core/) | 2.0.0 | `npm install anosys-sdk-core` |
| <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/openai-dark.svg"><img src="assets/logos/openai-light.svg" width="16" height="16" alt=""></picture> [anosys-sdk-openai](packages/js/openai/) | 1.1.0 | `npm install anosys-sdk-openai openai` |
| <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/openai-dark.svg"><img src="assets/logos/openai-light.svg" width="16" height="16" alt=""></picture> [anosys-sdk-openai-agents](packages/js/openai-agents/) | 1.1.0 | `npm install anosys-sdk-openai-agents @openai/agents` |
| <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/anthropic-dark.svg"><img src="assets/logos/anthropic-light.svg" width="16" height="16" alt=""></picture> [anosys-sdk-anthropic](packages/js/anthropic/) | 1.1.0 | `npm install anosys-sdk-anthropic @anthropic-ai/sdk` |
| <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/claude-dark.svg"><img src="assets/logos/claude-light.svg" width="16" height="16" alt=""></picture> [anosys-sdk-claude-agents](packages/js/claude-agents/) | 1.1.0 | `npm install anosys-sdk-claude-agents @anthropic-ai/claude-agent-sdk` |
| <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/claude-dark.svg"><img src="assets/logos/claude-light.svg" width="16" height="16" alt=""></picture> [anosys-sdk-claude-code](packages/js/claude-code/) | 0.3.0 | `npx -y anosys-sdk-claude-code install` |
| <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/openai-dark.svg"><img src="assets/logos/openai-light.svg" width="16" height="16" alt=""></picture> [anosys-sdk-codex](packages/js/codex/) | 0.2.0 | `npm install -g anosys-sdk-codex` |
| <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/google-dark.svg"><img src="assets/logos/google-light.svg" width="16" height="16" alt=""></picture> [anosys-sdk-antigravity](packages/js/antigravity/) | 0.2.0 | `npm install -g anosys-sdk-antigravity` |

</details>

## Contributing

```bash
make install-dev
make test
```

The JavaScript packages ship source modules and need no build step. CI covers Python 3.10, 3.11 and 3.12 and Node.js 18, 20 and 22. The example notebooks need provider and Anosys.ai keys.

## License

[Apache License 2.0](LICENSE).
