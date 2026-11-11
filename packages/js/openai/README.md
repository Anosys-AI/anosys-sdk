# anosys-sdk-openai (JS)

AnoSys SDK for OpenAI — automatic instrumentation and logging for OpenAI API calls.

## Installation

```bash
npm install anosys-sdk-openai
```

## Quick Start

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

## Function Decorator

```js
import { anosysLogger } from 'anosys-sdk-openai';

const myFunction = anosysLogger('my_app.pipeline')(async (input) => {
  // your logic
  return result;
});
```

## Raw Logger

```js
import { anosysRawLogger } from 'anosys-sdk-openai';

await anosysRawLogger({ event: 'user_action', user_id: 'u123', value: 42 });
```

## User Context

```js
new AnosysOpenAILogger({
  getUserContext: () => ({ session_id: req.sessionId, token: req.token }),
});
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANOSYS_API_KEY` | Yes | Obtain from https://console.anosys.ai |
| `OPENAI_API_KEY` | Yes | OpenAI API key |
| `ANOSYS_API_URL` | No | Override logging endpoint |
| `ANOSYS_RESOLVER_URL` | No | Override API key resolver |
| `ANOSYS_LOG_LEVEL` | No | `debug` / `info` / `warn` / `error` / `silent` (default: `warn`) |

## Content controls

See the [content-controls reference](../../../DATA_CONTROLS.md) for encryption coverage, default columns, size limits, and limitations. Encryption is opt-in and applies to selected string fields; it does not encrypt the complete record.

Collection follows one level for every AnoSys SDK: `ANOSYS_COLLECTION_LEVEL=full` (default), `metadata` (no prompts, completions or tool data) or `off`, a project `.anosys` file can only lower it, and `ANOSYS_DISABLE=1` stops all sending. Without an API key nothing is sent. Telemetry is sent in the background and never delays your calls. See the [data-collection policy](../../../PRIVACY.md).
