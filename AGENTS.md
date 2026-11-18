# AGENTS.md

Instructions for AI coding agents (Claude Code, Codex, Cursor and others). Use the first part when you add Anosys.ai to a user's project, and the second part when you work in this repository.

## Add Anosys.ai to a project

1. **Find what the project uses** and pick the matching package:

   | The project uses | Python | JavaScript | Create once at startup |
   | --- | --- | --- | --- |
   | OpenAI SDK (also OpenRouter and LangChain on OpenAI) | `anosys-sdk-openai` | `anosys-sdk-openai` | `AnosysOpenAILogger()` |
   | Anthropic SDK | `anosys-sdk-anthropic` | `anosys-sdk-anthropic` | `AnosysAnthropicLogger()` |
   | OpenAI Agents SDK | `anosys-sdk-openai-agents` | `anosys-sdk-openai-agents` | Python: `add_trace_processor(AnosysOpenAIAgentsLogger())`; JS: `addTracingProcessor(new AnosysOpenAIAgentsLogger())` |
   | Claude Agent SDK | `anosys-sdk-claude-agents` | `anosys-sdk-claude-agents` | Python: `AnosysClaudeAgentsLogger()` before importing `query`; JS: `new AnosysClaudeAgentsLogger()`, then use `wrapQuery(query)` |
   | Plain functions to trace | `anosys-sdk-core` | any package above, for example `anosys-sdk-openai` | Python: the `@anosys_logger` decorator; JS: `anosysLogger` |

2. **Install it** with the project's package manager (pip, uv, poetry, npm, pnpm, yarn), next to the provider SDK the project already uses.
3. **Create the logger once**, at application startup, **before** any OpenAI or Anthropic client is created. Do not create it per request.
4. **Read the key from the environment.** The SDK reads `ANOSYS_API_KEY`. Never hard-code a key or commit one; add `ANOSYS_API_KEY=` to the project's `.env.example` if it has one.
5. **Respect privacy settings.** Application SDKs send prompts and responses by default. If the project handles sensitive data, pass `capture_content=False` (Python) or `captureContent: false` (JavaScript), or tell the user about `ANOSYS_COLLECTION_LEVEL=metadata`. Never remove an existing `ANOSYS_DISABLE`, `ANOSYS_COLLECTION_LEVEL` or `.anosys` setting.
6. **Verify:** run the app once and tell the user to open the [Console](https://console.anosys.ai) to see the call. If the SDK logs `telemetry is disabled`, the key is missing or wrong.

Coding-assistant tracking (Claude Code, Codex, Antigravity) is installed by the user with one command, not added to project code; see [Track coding-assistant spend](README.md#track-coding-assistant-spend).

**Connect yourself to Anosys.ai data.** If the user wants you to read their Anosys.ai traces, problems or evals, run `npx -y anosys-sdk-mcp install --target <your tool> -y` with `ANOSYS_MCP_API_KEY` (an `ak_mcp_...` key from the Console, not the ingestion key) already exported. Never ask the user to paste the key into the chat, and never write it into a project file; `--workspace` writes a reference to the variable instead. See [anosys-sdk-mcp](packages/js/mcp/README.md).

Package guides: [packages/python](packages/python) and [packages/js](packages/js). Data controls: [docs/DATA_CONTROLS.md](docs/DATA_CONTROLS.md).

## Work in this repository

- **Layout:** Python packages in `packages/python/<name>`, JavaScript packages in `packages/js/<name>`; every integration exists in both languages and they must behave the same.
- **Set up:** `make install-dev`. **Test:** `make test`. **Lint:** `make lint`.
- **Change both languages together.** A fix or feature in one language's integration usually needs the same change in the other, with tests in both.
- **Privacy is a hard rule.** Content (prompts, responses, tool input and output) must never be sent at the `metadata` level, and every content field must be encrypted when `ANOSYS_ENCRYPTION_KEY` is set. Add a test for any new field you send.
- **Never commit** API keys, prompts, customer data or real transcripts, including in tests, fixtures and notebooks.
- Follow [CONTRIBUTING.md](CONTRIBUTING.md) for pull requests.
