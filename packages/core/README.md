# AnoSys SDK Core

Core utilities for the AnoSys SDK - shared functionality for all AnoSys integrations.

## Installation

```bash
pip install anosys-sdk-core
```

## Usage

### Function Decorators

```python
from anosys_sdk_core import anosys_logger, anosys_raw_logger, setup_api
import os

os.environ["ANOSYS_API_KEY"] = "your-api-key"

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

## API Reference

- `anosys_logger(source=None)` - Decorator to log function calls
- `anosys_raw_logger(data)` - Log arbitrary data directly
- `setup_api(path=None)` - Configure API endpoint

## License

MIT
