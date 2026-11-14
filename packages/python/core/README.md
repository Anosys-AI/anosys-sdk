<p align="center">
  <a href="https://anosys.ai">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/anosys-ai/anosys-sdk/main/assets/anosys-new-white-darkmode.svg">
      <img src="https://raw.githubusercontent.com/anosys-ai/anosys-sdk/main/assets/anosys-new-black-lightmode.svg" alt="Anosys.ai" width="240">
    </picture>
  </a>
</p>

# AnoSys SDK Core

Core utilities for the AnoSys SDK - shared functionality for all AnoSys integrations.

## Installation

Requires Python 3.10 or later.

```bash
pip install anosys-sdk-core
```

## Usage

### Function Decorators

```python
from anosys_sdk_core import anosys_logger, anosys_raw_logger, setup_api
import os

os.environ["ANOSYS_API_KEY"] = "your-api-key"
setup_api()

# Decorator for automatic logging
@anosys_logger(source="my_app")
def my_function(data):
    return process(data)

# Async functions work too
@anosys_logger(source="my_app.async")
async def my_async_function(data):
    return await async_process(data)

# Raw logging
anosys_raw_logger({
    "event": "custom_event",
    "data": {"key": "value"}
})
```

## Shared telemetry mapping

Core 1.1.0 adds `extract_genai_span_info` and `CLAUDE_KEY_MAPPING` for Anthropic and Claude Agent SDK spans. It also provides client-side field encryption shared by the Python integrations.

## API Reference

- `anosys_logger(source=None)` - Decorator to log function calls
- `anosys_raw_logger(data)` - Log arbitrary data directly
- `setup_api(path=None)` - Configure API endpoint

## License

Apache 2.0

## Content controls

See the [content-controls reference](../../../DATA_CONTROLS.md) for encryption coverage, default columns, size limits, and limitations. Encryption is opt-in and applies to selected string fields; it does not encrypt the complete record.

Collection follows one level for every AnoSys SDK: `ANOSYS_COLLECTION_LEVEL=full` (default), `metadata` (no prompts, completions or tool data) or `off`, a project `.anosys` file can only lower it, and `ANOSYS_DISABLE=1` stops all sending. Without an API key nothing is sent. Telemetry is sent in the background and never delays your calls. See the [data-collection policy](../../../PRIVACY.md).
