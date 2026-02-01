"""
Data batching and CVS variable mapping utilities for AnoSys SDK.

Provides functions to transform data into the CVS format expected by the AnoSys API.
"""

import json
from typing import Any, Dict, Optional, Union

from anosys_sdk_core.models import DEFAULT_STARTING_INDICES


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
        return "float"
    elif isinstance(value, str):
        return "string"
    else:
        return "string"


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
        
        # Try to interpret as number
        try:
            if '.' in var_value:
                variables[variable] = float(var_value)
            else:
                variables[variable] = int(var_value)
            return
        except ValueError:
            pass
        
        # Store as plain string
        variables[variable] = var_value
        return
    
    # Fallback
    variables[variable] = var_value


def reassign(
    data: Union[Dict[str, Any], str],
    key_to_cvs: Dict[str, str],
    starting_indices: Optional[Dict[str, int]] = None
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
    
    indices = (starting_indices or DEFAULT_STARTING_INDICES).copy()
    
    for key, value in data.items():
        if value is None:
            continue
        
        value_type = _get_type_key(value)
        prefix, index_key = _get_prefix_and_index(value_type)
        
        # Get or assign CVS variable name
        if key not in key_to_cvs:
            key_to_cvs[key] = f"{prefix}{indices[index_key]}"
            indices[index_key] += 1
        
        cvs_var = key_to_cvs[key]
        
        # Convert value to appropriate format
        if isinstance(value, (dict, list)):
            cvs_vars[cvs_var] = json.dumps(value)
        elif isinstance(value, (bool, int, float)):
            cvs_vars[cvs_var] = value
        else:
            cvs_vars[cvs_var] = str(value)
    
    return cvs_vars
