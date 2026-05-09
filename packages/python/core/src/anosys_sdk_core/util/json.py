"""
JSON utility functions for AnoSys SDK.

Provides safe JSON serialization and conversion utilities.
"""

import json
from datetime import datetime
from typing import Any, Optional


def format_timestamp(val: Any) -> Optional[str]:
    """
    Format a value as a UTC ISO timestamp ending in 'Z'.
    
    Handles datetime objects and strings. Ensures +00:00 is replaced by Z.
    """
    if val is None:
        return None
    
    if isinstance(val, datetime):
        iso = val.isoformat()
    else:
        iso = str(val)
    
    # Handle the common Python isoformat() output
    if "+00:00" in iso:
        return iso.replace("+00:00", "Z")
    
    # If it's a timestamp-like string but missing Z
    if "T" in iso and not iso.endswith("Z") and "+" not in iso:
        return iso + "Z"
        
    return iso


def to_json_fallback(resp: Any) -> Any:
    """
    Safely convert an object to a JSON-serializable form.
    
    Handles Pydantic models, dictionaries, and other objects gracefully.
    
    Args:
        resp: Object to convert
        
    Returns:
        JSON-serializable representation
    """
    try:
        if isinstance(resp, (str, int, float, bool, type(None))):
            return resp
        if hasattr(resp, "model_dump"):
            return resp.model_dump()
        if hasattr(resp, "dict"):
            return resp.dict()
        if isinstance(resp, (dict, list)):
            return resp
        return str(resp)
    except Exception as e:
        return {"error": str(e), "output": str(resp)}


def to_str_or_none(val: Any) -> Optional[str]:
    """
    Convert a value to string, handling dicts/lists as JSON.
    
    Args:
        val: Value to convert
        
    Returns:
        String representation or None
    """
    if val is None:
        return None
    if isinstance(val, (dict, list)):
        return json.dumps(val)
    return str(val)


def safe_serialize(obj: Any) -> Any:
    """
    Recursively serialize an object to JSON-safe values.
    
    Handles nested objects, Pydantic models, and custom classes.
    
    Args:
        obj: Object to serialize
        
    Returns:
        JSON-safe representation
    """
    try:
        if isinstance(obj, (str, int, float, bool)) or obj is None:
            return obj
        elif isinstance(obj, list):
            return [safe_serialize(i) for i in obj]
        elif isinstance(obj, dict):
            return {k: safe_serialize(v) for k, v in obj.items()}
        elif hasattr(obj, "dict"):
            return safe_serialize(obj.dict())
        elif hasattr(obj, "export"):
            return safe_serialize(obj.export())
        elif hasattr(obj, "__dict__"):
            return safe_serialize(vars(obj))
        return str(obj)
    except Exception as e:
        return f"[Unserializable: {e}]"
