"""
Data batching and CVS variable mapping utilities for AnoSys SDK.

Provides functions to transform data into the CVS format expected by the AnoSys API.
"""

import json
import logging
import math
from typing import Any, Dict, Optional, Union

from anosys_sdk_core.models import (
    DEFAULT_STARTING_INDICES, 
    OTEL_AI_VALID_TYPES,
    CLAUDE_VALID_TYPES
)

logger = logging.getLogger(__name__)

# Attributes dropped because their type's columns were used up (warned once each)
_DROPPED_KEYS: set = set()


def _get_type_key(value: Any) -> str:
    """
    Map Python types to category keys.
    
    Args:
        value: Value to determine type for
        
    Returns:
        Type category string
    """
    if isinstance(value, bool):
        return "bool"
    elif isinstance(value, int) and not isinstance(value, bool):
        return "int"
    elif isinstance(value, float):
        return "float" if math.isfinite(value) else "string"
    elif isinstance(value, str):
        return "string"
    else:
        return "string"


# Custom-variable columns that exist in every AnoSys schema
SLOT_LIMITS = {"cvs": 200, "cvn": 200, "cvb": 100}
# Fixed meaning (consent, raw record, source tag): never handed to a dynamic key
RESERVED_SLOTS = frozenset({"cvs198", "cvs199", "cvs200"})


def _allocate_slot(prefix: str, start: int, used: set) -> Optional[str]:
    """
    The first free ``prefix<N>`` column from ``start``, or None when the type's
    columns are used up. ``used`` holds every column already taken by a fixed
    or earlier dynamic key and is updated.
    """
    index = max(1, int(start))
    limit = SLOT_LIMITS.get(prefix, 200)
    while index <= limit:
        slot = f"{prefix}{index}"
        if slot not in used and slot not in RESERVED_SLOTS:
            used.add(slot)
            return slot
        index += 1
    return None


def _get_prefix_and_index(value_type: str) -> tuple:
    """
    Get the CVS prefix and index key for a value type.
    
    Args:
        value_type: Type category from _get_type_key
        
    Returns:
        Tuple of (prefix, index_key)
    """
    if value_type == "string":
        return "cvs", "string"
    elif value_type in ("int", "float"):
        return "cvn", "number"
    elif value_type == "bool":
        return "cvb", "bool"
    else:
        return "cvs", "string"


def assign(variables: Dict[str, Any], variable: str, var_value: Any) -> None:
    """
    Safely assign a value to a variables dictionary.
    
    Handles JSON strings, numeric conversion, and type coercion.
    
    Args:
        variables: Dictionary to assign to
        variable: Key name
        var_value: Value to assign
    """
    if var_value is None:
        variables[variable] = None
        return
    
    # Handle booleans first (before int check since bool is subclass of int)
    if isinstance(var_value, bool):
        variables[variable] = var_value
        return
    
    # Handle numbers
    if isinstance(var_value, (int, float)):
        variables[variable] = var_value
        return
    
    # Handle dicts and lists as JSON
    if isinstance(var_value, (dict, list)):
        variables[variable] = json.dumps(var_value)
        return
    
    # Handle strings
    if isinstance(var_value, str):
        var_value = var_value.strip()
        
        # Try to parse as JSON if it looks like JSON
        if var_value.startswith(('{', '[')):
            try:
                parsed = json.loads(var_value)
                variables[variable] = json.dumps(parsed)
                return
            except json.JSONDecodeError:
                pass
        
        # Store as plain string
        variables[variable] = var_value
        return

    
    # Fallback
    variables[variable] = var_value


def reassign(
    data: Union[Dict[str, Any], str],
    key_to_cvs: Dict[str, str],
    starting_indices: Optional[Dict[str, int]] = None,
    valid_types: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Map dictionary keys to CVS variable names.
    
    Transforms a regular dictionary into one keyed by CVS variable names
    (cvs1, cvs2, cvn1, cvb1, etc.) for the AnoSys API.
    
    Args:
        data: Dictionary or JSON string to transform
        key_to_cvs: Mapping of logical keys to CVS variable names
        starting_indices: Starting indices for each type category
        
    Returns:
        Dictionary with CVS variable keys
    """
    cvs_vars: Dict[str, Any] = {}
    
    if isinstance(data, str):
        data = json.loads(data)
    
    if not isinstance(data, dict):
        raise ValueError("Input must be a dict or JSON string representing a dict")

    # Detect source and use appropriate valid types if not provided
    if valid_types is None:
        source = data.get("from_source") or data.get("source") or data.get("cvs200")
        if source in ("ClaudeCodeHook", "CodexHook", "AntigravityHook"):
            valid_types = CLAUDE_VALID_TYPES
        else:
            valid_types = OTEL_AI_VALID_TYPES
    
    indices = (starting_indices or DEFAULT_STARTING_INDICES).copy()
    # Columns already taken: a new key never shares a column with another key,
    # whether that key is fixed, reserved, or was allocated in an earlier call.
    used = set(key_to_cvs.values())
    
    for key, value in data.items():
        if value is None:
            continue
        
        value_type = _get_type_key(value)
        prefix, index_key = _get_prefix_and_index(value_type)
        
        # Get or assign CVS variable name
        if key not in key_to_cvs:
            slot = _allocate_slot(prefix, indices[index_key], used)
            if slot is None:
                if key not in _DROPPED_KEYS:
                    _DROPPED_KEYS.add(key)
                    logger.warning("No free %s column for attribute %r; it is not sent", prefix, key)
                continue
            key_to_cvs[key] = slot
            indices[index_key] = int(slot[3:]) + 1
        
        cvs_var = key_to_cvs[key]
        
        # Enforce type based on the detected validation table
        expected_type = valid_types.get(cvs_var) or valid_types.get(key)
        
        if expected_type == "double":
            try:
                # Handle numeric conversion
                if value is None or (isinstance(value, str) and value.strip() == ""):
                    cvs_vars[cvs_var] = 0.0
                else:
                    f_val = float(value)
                    cvs_vars[cvs_var] = f_val if math.isfinite(f_val) else 0.0
            except (ValueError, TypeError):
                cvs_vars[cvs_var] = 0.0
        elif expected_type == "boolean":
            if isinstance(value, str):
                cvs_vars[cvs_var] = value.lower() in ("true", "1", "yes")
            else:
                cvs_vars[cvs_var] = bool(value)
        elif expected_type == "json" or expected_type == "array<double>":
            if isinstance(value, (dict, list)):
                cvs_vars[cvs_var] = json.dumps(value)
            else:
                cvs_vars[cvs_var] = str(value)
        elif expected_type == "timestamp":
            cvs_vars[cvs_var] = str(value)
        elif cvs_var.startswith("cvs"):
            # Fallback for CVS prefix (String)
            if isinstance(value, (dict, list)):
                cvs_vars[cvs_var] = json.dumps(value)
            else:
                cvs_vars[cvs_var] = str(value)
        elif cvs_var.startswith("cvn") or (cvs_var.startswith("g") and cvs_var[1:].isdigit()):
            # Fallback for CVN/G prefix (Number)
            try:
                if value is None or (isinstance(value, str) and value.strip() == ""):
                    cvs_vars[cvs_var] = 0
                else:
                    f_val = float(str(value))
                    if not math.isfinite(f_val):
                        cvs_vars[cvs_var] = 0
                    else:
                        cvs_vars[cvs_var] = int(f_val) if f_val == int(f_val) else f_val
            except (ValueError, TypeError, OverflowError):
                cvs_vars[cvs_var] = 0
        elif cvs_var.startswith("cvb"):
            # Fallback for CVB prefix (Boolean)
            if isinstance(value, str):
                cvs_vars[cvs_var] = value.lower() in ("true", "1", "yes")
            else:
                cvs_vars[cvs_var] = bool(value)
        else:
            # Final fallback: Treat as string if it doesn't match any special rule
            if isinstance(value, (dict, list)):
                cvs_vars[cvs_var] = json.dumps(value)
            else:
                cvs_vars[cvs_var] = str(value)

    if "custom_mapping" in data and "otel_schema_url" in cvs_vars:
        cvs_vars["otel_schema_url"] = json.dumps(key_to_cvs)

    return cvs_vars
