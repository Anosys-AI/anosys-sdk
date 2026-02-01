"""
Utility functions for OpenAI Agents SDK.

Provides serialization and helper utilities specific to the agents package.
"""

from typing import Any


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


def clean_nulls(data: Any) -> Any:
    """
    Recursively remove None values and empty containers.
    
    Args:
        data: Data structure to clean
        
    Returns:
        Cleaned data structure
    """
    if isinstance(data, dict):
        cleaned = {k: clean_nulls(v) for k, v in data.items() if v is not None}
        return {k: v for k, v in cleaned.items() if v not in ({}, [], None)}
    elif isinstance(data, list):
        cleaned = [clean_nulls(item) for item in data if item is not None]
        return [item for item in cleaned if item not in ({}, [], None)]
    return data
