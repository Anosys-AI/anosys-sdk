# anosys-sdk-anthropic

AnoSys SDK for Anthropic (Node.js): automatically capture Anthropic (Claude) API calls and send them to [AnoSys](https://anosys.ai).

It exports the OpenTelemetry spans that `@anthropic-ai/sdk` emits natively, so no third-party instrumentor is involved. Records use the same columns as the Python package and the OpenAI integrations.

## Installation

```bash
npm install anosys-sdk-anthropic @anthropic-ai/sdk
```

Requires `@anthropic-ai/sdk>=1.0.0` and Node 18+.

## Quick Start

```javascript
import Anthropic from '@anthropic-ai/sdk';
import { AnosysAnthropicLogger } from 'anosys-sdk-anthropic';

// Once at startup, before creating clients
new AnosysAnthropicLogger();

const client = new Anthropic();
const message = await client.messages.create({
  model: 'claude-sonnet-5-5',
  max_tokens: 1024,
  messages: [{ role: 'user', content: 'Hello!' }],
});
```

## Options

```javascript
new AnosysAnthropicLogger({
  getUserContext: () => ({ session_id: 'abc', token: 'user-token' }),
  captureContent: true,     // record prompts and completions (default)
  useBatchProcessor: false,
});
```

`captureContent` sets `ANTHROPIC_OPEN_TELEMETRY_TRACES_CONTENT_MODE=content` when it is not already set; the SDK reads it when a client is constructed. A client given its own `openTelemetry` option uses that instead.

The logger registers a global tracer provider. If your application already registered one, pass ours to the client: `new Anthropic({ openTelemetry: { tracerProvider: getTracerProvider() } })`. Make sure a single `@opentelemetry/api` version is installed (`npm dedupe`), otherwise the SDK cannot see the registered provider.

## What Data is Captured?

Same as the [Python package](../../python/anthropic/README.md): model and request parameters, response id and stop reason, usage (input tokens include cached tokens), prompt-cache tokens (`cvn4`, `cvn5`), extended thinking (`cvb3`), system instructions and messages. Records are tagged `cvs200 = "AnthropicTelemetry"`.

## License

Apache-2.0
