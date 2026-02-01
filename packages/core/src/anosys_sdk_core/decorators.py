"""
Function decorators for AnoSys logging.

Provides decorators to automatically log function inputs, outputs, and errors.
"""

import asyncio
import inspect
import io
import json
import sys
import traceback
from functools import wraps
from typing import Any, Callable, Dict, Optional

import requests

from anosys_sdk_core.config import resolve_api_key
from anosys_sdk_core.models import BASE_KEY_MAPPING, DEFAULT_STARTING_INDICES
from anosys_sdk_core.util.json import to_json_fallback, to_str_or_none
from anosys_sdk_core.util.batching import assign, reassign

# Global configuration
_log_api_url: str = "https://www.anosys.ai"
_key_to_cvs: Dict[str, str] = BASE_KEY_MAPPING.copy()
_starting_indices: Dict[str, int] = DEFAULT_STARTING_INDICES.copy()


def setup_api(path: Optional[str] = None, starting_indices: Optional[Dict[str, int]] = None) -> None:
    """
    Configure the logging API endpoint and indices.
    
    Args:
        path: Override API URL (skips API key resolution if provided)
        starting_indices: Custom starting indices for CVS variables
    """
    global _log_api_url, _starting_indices
    
    if starting_indices:
        _starting_indices.update(starting_indices)
    
    if path:
        _log_api_url = path
    else:
        _log_api_url = resolve_api_key()


def _get_caller_info() -> Dict[str, Any]:
    """Get information about the caller of the decorated function."""
    stack = inspect.stack()
    if len(stack) > 3:
        caller_frame = stack[3]
        return {
            "function": caller_frame.function,
            "file": caller_frame.filename,
            "line": caller_frame.lineno,
        }
    return {"function": "unknown", "file": "unknown", "line": 0}


def _log_payload(
    source: Optional[str],
    args: tuple,
    output: Any,
    error_info: Optional[Dict[str, Any]],
    caller_info: Dict[str, Any]
) -> None:
    """Send the logging payload to AnoSys API."""
    global _key_to_cvs, _starting_indices, _log_api_url
    
    variables: Dict[str, Any] = {}
    
    print(f"[ANOSYS] Logger (source={source}) "
          f"called from {caller_info['function']} "
          f"at {caller_info['file']}:{caller_info['line']}")
    
    if error_info:
        print(f"[ANOSYS] Error occurred: {error_info['message']}")
    else:
        out_str = str(output)
        if len(out_str) > 200:
            out_str = out_str[:200] + "..."
        print(f"[ANOSYS] Captured output: {out_str}")
    
    # Prepare payload
    input_array = [to_str_or_none(arg) for arg in args]
    assign(variables, "source", to_str_or_none(source))
    assign(variables, 'custom_mapping', json.dumps(_key_to_cvs, indent=4))
    assign(variables, "input", input_array)
    
    if error_info:
        assign(variables, "error", True)
        assign(variables, "error_type", error_info["type"])
        assign(variables, "error_message", error_info["message"])
        assign(variables, "error_stack", error_info["stack"])
        assign(variables, "output", None)
    else:
        assign(variables, "output", to_json_fallback(output))
    
    assign(variables, "caller", caller_info)
    
    # Send log
    try:
        mapped_data = reassign(variables, _key_to_cvs, _starting_indices)
        response = requests.post(_log_api_url, json=mapped_data, timeout=5)
        response.raise_for_status()
        print("[ANOSYS] Logged successfully")
    except Exception as e:
        print(f"[ANOSYS]❌ POST failed: {e}")


def _handle_logging_sync(func: Callable, args: tuple, kwargs: dict, source: Optional[str]) -> Any:
    """Handle logging for synchronous functions."""
    caller_info = _get_caller_info()
    
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    
    text = None
    error_info = None
    
    try:
        text = func(*args, **kwargs)
    except Exception as e:
        error_info = {
            "type": type(e).__name__,
            "message": str(e),
            "stack": traceback.format_exc()
        }
        raise
    finally:
        printed_output = sys.stdout.getvalue()
        sys.stdout = old_stdout
        output = text if text else printed_output.strip()
        _log_payload(source, args, output, error_info, caller_info)
    
    return text


async def _handle_logging_async(func: Callable, args: tuple, kwargs: dict, source: Optional[str]) -> Any:
    """Handle logging for async functions."""
    caller_info = _get_caller_info()
    
    text = None
    error_info = None
    
    try:
        text = await func(*args, **kwargs)
    except Exception as e:
        error_info = {
            "type": type(e).__name__,
            "message": str(e),
            "stack": traceback.format_exc()
        }
        raise
    finally:
        _log_payload(source, args, text, error_info, caller_info)
    
    return text


async def _handle_logging_async_gen(func: Callable, args: tuple, kwargs: dict, source: Optional[str]):
    """Handle logging for async generator functions."""
    caller_info = _get_caller_info()
    
    aggregated_output = []
    error_info = None
    
    try:
        async for item in func(*args, **kwargs):
            aggregated_output.append(item)
            yield item
    except Exception as e:
        error_info = {
            "type": type(e).__name__,
            "message": str(e),
            "stack": traceback.format_exc()
        }
        raise
    finally:
        # Join strings if possible
        if all(isinstance(x, str) for x in aggregated_output):
            output = "".join(aggregated_output)
        else:
            output = aggregated_output
        
        _log_payload(source, args, output, error_info, caller_info)


def anosys_logger(source: Optional[str] = None) -> Callable:
    """
    Decorator to log function input/output to AnoSys API.
    
    Supports sync, async, and async generator functions.
    Captures caller information and error stack traces.
    
    Args:
        source: Source identifier for the logged function
        
    Returns:
        Decorated function
        
    Example:
        @anosys_logger(source="my_app.calculations")
        def calculate(data):
            return sum(data)
    """
    def decorator(func: Callable) -> Callable:
        if inspect.isasyncgenfunction(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                async for item in _handle_logging_async_gen(func, args, kwargs, source):
                    yield item
            return wrapper
        elif asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                return await _handle_logging_async(func, args, kwargs, source)
            return wrapper
        else:
            @wraps(func)
            def wrapper(*args, **kwargs):
                return _handle_logging_sync(func, args, kwargs, source)
            return wrapper
    return decorator


def anosys_raw_logger(data: Optional[Dict[str, Any]] = None) -> Optional[requests.Response]:
    """
    Directly log raw data to AnoSys API.
    
    Args:
        data: Dictionary of data to log
        
    Returns:
        Response object on success, None on failure
        
    Example:
        anosys_raw_logger({
            "event": "user_action",
            "action": "button_click",
            "user_id": "12345"
        })
    """
    global _key_to_cvs, _starting_indices, _log_api_url
    
    if data is None:
        data = {}
    
    try:
        mapped_data = reassign(data, _key_to_cvs, _starting_indices)
        response = requests.post(_log_api_url, json=mapped_data, timeout=5)
        response.raise_for_status()
        print("[ANOSYS] Raw logger: Data logged successfully")
        return response
    except Exception as err:
        print(f"[ANOSYS]❌ POST failed: {err}")
        return None
