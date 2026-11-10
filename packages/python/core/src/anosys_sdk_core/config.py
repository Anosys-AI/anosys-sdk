"""
Configuration management for AnoSys SDK.

Handles API key resolution, URL configuration, and environment variable parsing.
"""

import logging
import os
from typing import Optional

import requests
from dotenv import dotenv_values

# Load only safe API configuration variables from .env (never overwrite os.environ
# and never load untrusted variables such as ANOSYS_CONSENT_FILE or hook endpoints).
_SAFE_DOTENV_KEYS = ("ANOSYS_API_KEY", "ANOSYS_API_URL", "ANOSYS_RESOLVER_URL")
try:
    for _k, _v in dotenv_values().items():
        if _k in _SAFE_DOTENV_KEYS and _v is not None and _k not in os.environ:
            os.environ[_k] = _v
except Exception:
    pass

logger = logging.getLogger(__name__)

# Default API endpoints — override via environment variables for custom deployments
DEFAULT_API_URL = os.getenv("ANOSYS_API_URL", "https://www.anosys.ai")
API_KEY_RESOLVER_URL = os.getenv("ANOSYS_RESOLVER_URL", "https://console.anosys.ai/api/resolveapikeys")



def get_env_bool(var_name: str, default: bool = True) -> bool:
    """
    Get a boolean value from an environment variable.
    
    Args:
        var_name: Name of the environment variable
        default: Default value if variable is not set
        
    Returns:
        Boolean value from the environment variable
    """
    value = os.getenv(var_name)
    
    if value is None:
        return default
    
    value_str = value.strip().lower()
    if value_str in ('1', 'true', 'yes', 'on'):
        return True
    elif value_str in ('0', 'false', 'no', 'off'):
        return False
    else:
        return bool(value_str)


def resolve_api_key(api_key: Optional[str] = None, timeout: int = 10) -> str:
    """
    Resolve the API key to the ingestion URL for this key.

    Returns "" when there is no key or it cannot be resolved: nothing is sent
    then (telemetry is never posted to a default site).

    Args:
        api_key: AnoSys API key (defaults to ANOSYS_API_KEY env var)
        timeout: Request timeout in seconds
    """
    explicit = os.getenv("ANOSYS_API_URL", "").strip()
    if explicit:
        return explicit  # a self-hosted or test endpoint set on purpose

    if api_key is None:
        api_key = os.getenv('ANOSYS_API_KEY')

    if not api_key:
        logger.warning("ANOSYS_API_KEY not found; AnoSys telemetry is disabled. Get a key at "
                       "https://console.anosys.ai/collect/integrationoptions")
        return ""

    resolver_url = os.getenv("ANOSYS_RESOLVER_URL") or API_KEY_RESOLVER_URL
    try:
        response = requests.get(resolver_url, params={"apikey": api_key}, timeout=timeout)
        response.raise_for_status()
        url = response.json().get("apiUrl") or ""
        if not url:
            logger.error("The AnoSys API key was not recognised; telemetry is disabled")
        return url
    except (requests.exceptions.RequestException, ValueError) as e:
        # the key is never logged
        logger.error("Could not resolve the AnoSys API key (%s); telemetry is disabled", type(e).__name__)
        return ""


def get_api_url(override_url: Optional[str] = None) -> str:
    """
    Get the API URL for logging.
    
    Args:
        override_url: Optional URL to use instead of resolving
        
    Returns:
        The API URL to use for logging
    """
    if override_url:
        return override_url
    return resolve_api_key()
