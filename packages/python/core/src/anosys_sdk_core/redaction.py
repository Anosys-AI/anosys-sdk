"""
Redaction utilities for AnoSys SDK.

Provides utilities for redacting sensitive information before logging.
redact_string: PII patterns (OpenAI Agents pii_redaction); scrub_secrets: credentials (hooks).
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


# Secret-shaped strings scrubbed from hook content even at ``full`` (best effort)
SECRET_PATTERNS: List[Pattern] = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bASIA[0-9A-Z]{16}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}\b"),
    re.compile(r"\bxox[abpr]-[A-Za-z0-9\-]{10,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"),  # JWT
    re.compile(
        r"(?i)((?:api[_-]?key|apikey|secret|password|passwd|token|authorization)[\"']?\s*[:=]\s*[\"']?(?:bearer\s+)?)"
        r"[A-Za-z0-9_\-/+=.]{12,}"
    ),
]
SECRET_REPLACEMENT = "[SECRET]"


def scrub_secrets(value: Any) -> Any:
    """
    Replace secret-shaped substrings (API keys, tokens, private keys) in a
    string, or in every string inside a dict/list. Best effort: it catches
    common key formats, not every secret.
    """
    if isinstance(value, str):
        result = value
        for pattern in SECRET_PATTERNS:
            if pattern.groups:
                result = pattern.sub(lambda m: m.group(1) + SECRET_REPLACEMENT, result)
            else:
                result = pattern.sub(SECRET_REPLACEMENT, result)
        return result
    if isinstance(value, dict):
        return {k: scrub_secrets(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub_secrets(v) for v in value]
    return value
