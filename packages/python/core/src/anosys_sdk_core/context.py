"""
User context management for AnoSys SDK.

Provides utilities for managing user context (session ID, token, etc.) across requests.
"""

import contextvars
from typing import Any, Dict, Optional

# Context variable for storing user context
_user_context: contextvars.ContextVar[Optional[Dict[str, Any]]] = contextvars.ContextVar(
    'anosys_user_context',
    default=None
)


def set_user_context(context: Dict[str, Any]) -> None:
    """
    Set the current user context.
    
    Args:
        context: Dictionary containing user context (session_id, token, etc.)
    """
    _user_context.set(context)


def get_user_context() -> Optional[Dict[str, Any]]:
    """
    Get the current user context.
    
    Returns:
        The current user context dictionary, or None if not set
    """
    try:
        return _user_context.get()
    except LookupError:
        return None


def clear_user_context() -> None:
    """Clear the current user context."""
    _user_context.set(None)


def extract_session_id(context: Optional[Dict[str, Any]] = None) -> str:
    """
    Extract session ID from context.
    
    Args:
        context: User context dict (uses current context if None)
        
    Returns:
        Session ID string or "unknown_session"
    """
    if context is None:
        context = get_user_context()
    
    if context is None:
        return "unknown_session"
    
    if isinstance(context, dict):
        return context.get("session_id", "unknown_session")
    
    return getattr(context, "session_id", "unknown_session")


def extract_token(context: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """
    Extract token from context.
    
    Args:
        context: User context dict (uses current context if None)
        
    Returns:
        Token string or None
    """
    if context is None:
        context = get_user_context()
    
    if context is None:
        return None
    
    if isinstance(context, dict):
        return context.get("token")
    
    return getattr(context, "token", None)


def clean_contextvars(obj: Any) -> Any:
    """
    Recursively replace ContextVar objects with their values.
    
    Args:
        obj: Object to clean
        
    Returns:
        Cleaned object with ContextVars resolved
    """
    if isinstance(obj, contextvars.ContextVar):
        try:
            return obj.get()
        except LookupError:
            return None
    elif isinstance(obj, dict):
        return {key: clean_contextvars(value) for key, value in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return type(obj)(clean_contextvars(item) for item in obj)
    else:
        return obj
