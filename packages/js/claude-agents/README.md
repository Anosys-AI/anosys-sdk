# anosys-sdk-claude-agents

AnoSys SDK for the Claude Agent SDK (Node.js): trace agent runs, tools, subagents, tokens and cost, and send them to [AnoSys](https://anosys.ai).

## Installation

```bash
npm install anosys-sdk-claude-agents @anthropic-ai/claude-agent-sdk
```

## Quick Start

```javascript
import { query } from '@anthropic-ai/claude-agent-sdk';
import { AnosysClaudeAgentsLogger, wrapQuery } from 'anosys-sdk-claude-agents';

new AnosysClaudeAgentsLogger();
const tracedQuery = wrapQuery(query);

for await (const message of tracedQuery({
  prompt: 'List the files in this folder',
  options: { allowedTools: ['Bash', 'Read'] },
})) {
  console.log(message);
}
```

ES module exports cannot be patched, so wrap `query` once with `wrapQuery`. The returned Query keeps all its methods (`interrupt()`, `setPermissionMode()`, ...). For other message streams, use `traceMessages(stream, { prompt, options })`.

## Options

```javascript
new AnosysClaudeAgentsLogger({
  getUserContext: () => ({ session_id: 'abc', token: 'user-token' }),
  agentName: 'support_agent', // gen_ai.agent.name (default "claude_agent")
  captureContent: true,       // prompts, results, tool input/output (default)
  emitLlmSpans: false,        // one chat span per assistant response
  useBatchProcessor: false,
});
```

## What Data is Captured?

Same spans and attributes as the [Python package](../../python/claude_agents/README.md):

- `invoke_agent <agent_name>`: session id, model, prompt, result, total tokens (including cache), cost (`cvn7`)
- `execute_tool <tool>`: tool input, output and errors; subagent calls nest under their `Task` tool span
- `chat <model>` (opt-in): per-response usage

Records are tagged `cvs200 = "ClaudeAgentsTelemetry"`. This package builds on `anosys-sdk-anthropic` for the shared schema, exporter and tracer provider.

## License

Apache-2.0

## Content controls

See the [content-controls reference](../../../DATA_CONTROLS.md) for encryption coverage, default columns, redaction, and limitations. Encryption is opt-in and applies to selected string fields; it does not encrypt the complete record.
