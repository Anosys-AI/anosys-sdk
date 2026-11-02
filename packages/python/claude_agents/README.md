# AnoSys SDK for Claude Agents

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)

Automatically trace [Claude Agent SDK](https://docs.claude.com/en/api/agent-sdk/overview) runs and send them to [AnoSys](https://anosys.ai): agents, tools, subagents, tokens and cost.

## Installation

```bash
pip install anosys-sdk-claude-agents
```

## Quick Start

```python
import asyncio
from anosys_sdk_claude_agents import AnosysClaudeAgentsLogger

# Initialize once, before importing query (instruments query() and ClaudeSDKClient)
AnosysClaudeAgentsLogger()

from claude_agent_sdk import ClaudeAgentOptions, query


async def main():
    options = ClaudeAgentOptions(allowed_tools=["Bash", "Read"])
    async for message in query(prompt="List the Python files here", options=options):
        print(message)

asyncio.run(main())
```

`ClaudeSDKClient` is traced too: each `receive_response()` produces one agent run.

If `query` was imported before the logger was created, wrap it explicitly:

```python
from anosys_sdk_claude_agents import wrap_query
query = wrap_query(query)
```

For other message streams, use `trace_messages(stream, prompt=..., options=...)`.

## Options

```python
AnosysClaudeAgentsLogger(
    get_user_context=lambda: {"session_id": "abc", "token": "user-token"},
    agent_name="support_agent",   # gen_ai.agent.name (default "claude_agent")
    capture_content=True,          # prompts, results, tool input/output (default)
    emit_llm_spans=False,          # one chat span per assistant response
    use_batch_processor=False,
)
```

## What Data is Captured?

The Agent SDK runs the model inside a Claude Code subprocess, so the integration builds spans from the messages the run yields:

| Span | Name | Carries |
|---|---|---|
| Agent (root) | `invoke_agent <agent_name>` | session id (`gen_ai.conversation.id`), model, prompt, system prompt, final result, total tokens (including cache), cost (`cvn7`), turns |
| Tool | `execute_tool <tool>` | tool name and call id, input, output, errors |
| Subagent | `execute_tool Task` | subagent type as `gen_ai.agent.name`; the subagent's tool calls are nested under it |
| LLM (opt-in) | `chat <model>` | per-response model, stop reason, usage |

Token and cost totals live on the agent span. When `emit_llm_spans` is on, chat spans also carry per-call usage, so sum one or the other, not both.

The run span is the active span while the SDK works, so the Claude Code subprocess inherits the trace context (`TRACEPARENT`).

Records are tagged `cvs200 = "ClaudeAgentsTelemetry"` and use the same columns as `anosys-sdk-anthropic`. See [MAPPINGS.md](../../../MAPPINGS.md).

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANOSYS_API_KEY` | Yes | Your AnoSys API key |
| `ANTHROPIC_API_KEY` | Yes | Your Anthropic API key (used by Claude Code) |

## License

Apache 2.0
