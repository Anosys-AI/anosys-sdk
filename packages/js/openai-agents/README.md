# anosys-sdk-openai-agents (JS)

AnoSys SDK for OpenAI Agents — automatic instrumentation and logging for the OpenAI Agents SDK.

## Installation

```bash
npm install anosys-sdk-openai-agents
```

## Quick Start

```js
import { AnosysOpenAIAgentsLogger } from 'anosys-sdk-openai-agents';
import { Agent, run, addTracingProcessor } from '@openai/agents';

// Register the tracing processor — captures all agent traces automatically
const logger = new AnosysOpenAIAgentsLogger();
addTracingProcessor(logger);

const agent = new Agent({ name: 'my-agent', instructions: 'You are helpful.' });
const result = await run(agent, 'Hello');
```

## Function Decorator

```js
import { anosysLogger } from 'anosys-sdk-openai-agents';

const myTool = anosysLogger('my_tool')(async (input) => {
  return processInput(input);
});
```

## Raw Logger

```js
import { anosysRawLogger } from 'anosys-sdk-openai-agents';

await anosysRawLogger({ event: 'handoff_complete', from: 'triage', to: 'bq_agent' });
```

## User Context

```js
new AnosysOpenAIAgentsLogger({
  getUserContext: () => ({ session_id: ctx.sessionId, token: ctx.token }),
});
```

## Span Types Captured

`agent` · `function` · `generation` · `guardrail` · `handoff` · `response` · `custom` · `transcription` · `speech` · `speechgroup` · `MCPListTools` · `mcp_tools`

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANOSYS_API_KEY` | Yes | Obtain from https://console.anosys.ai |
| `OPENAI_API_KEY` | Yes | OpenAI API key |
| `ANOSYS_API_URL` | No | Override logging endpoint |
| `ANOSYS_RESOLVER_URL` | No | Override API key resolver |
| `ANOSYS_LOG_LEVEL` | No | `debug` / `info` / `warn` / `error` / `silent` (default: `warn`) |
