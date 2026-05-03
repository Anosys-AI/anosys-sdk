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
