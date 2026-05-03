"""
Redaction utilities for AnoSys SDK.

Provides utilities for redacting sensitive information before logging.
This module is a placeholder for future PII redaction functionality.
"""

import re
from typing import Any, Dict, List, Optional, Pattern


# Common patterns for sensitive data
PATTERNS: Dict[str, Pattern] = {
    "email": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
    "phone": re.compile(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'),
    "ssn": re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
    "credit_card": re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'),
    "api_key": re.compile(r'\b(sk-|pk-|api[-_]?key)[a-zA-Z0-9]{20,}\b', re.IGNORECASE),
}

# Placeholder text for redacted content
REDACTED = "[REDACTED]"


def redact_string(
    text: str,
    patterns: Optional[List[str]] = None,
    replacement: str = REDACTED
) -> str:
    """
    Redact sensitive patterns from a string.
    
    Args:
        text: Text to redact
        patterns: List of pattern names to apply (defaults to all)
        replacement: Replacement text for redacted content
        
    Returns:
        Text with sensitive content redacted
    """
    if patterns is None:
        patterns = list(PATTERNS.keys())
    
    result = text
    for pattern_name in patterns:
        if pattern_name in PATTERNS:
            result = PATTERNS[pattern_name].sub(replacement, result)
    
    return result


def redact_dict(
    data: Dict[str, Any],
    sensitive_keys: Optional[List[str]] = None,
    patterns: Optional[List[str]] = None,
    replacement: str = REDACTED
) -> Dict[str, Any]:
    """
    Redact sensitive data from a dictionary.
    
    Args:
        data: Dictionary to redact
        sensitive_keys: Keys to fully redact (e.g., ["password", "token"])
        patterns: Pattern names to apply to string values
        replacement: Replacement text
        
    Returns:
        Dictionary with sensitive content redacted
    """
    if sensitive_keys is None:
        sensitive_keys = ["password", "secret", "token", "api_key", "apikey"]
    
    result = {}
    for key, value in data.items():
        # Fully redact sensitive keys
        if any(sk.lower() in key.lower() for sk in sensitive_keys):
            result[key] = replacement
        elif isinstance(value, str):
            result[key] = redact_string(value, patterns, replacement)
        elif isinstance(value, dict):
            result[key] = redact_dict(value, sensitive_keys, patterns, replacement)
        elif isinstance(value, list):
            result[key] = [
                redact_dict(v, sensitive_keys, patterns, replacement) 
                if isinstance(v, dict) else v 
                for v in value
            ]
        else:
            result[key] = value
    
    return result
