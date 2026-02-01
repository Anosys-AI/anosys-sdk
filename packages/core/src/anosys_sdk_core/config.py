"""
Configuration management for AnoSys SDK.

Handles API key resolution, URL configuration, and environment variable parsing.
"""

import os
from typing import Optional

import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Default API endpoints
DEFAULT_API_URL = "https://www.anosys.ai"
API_KEY_RESOLVER_URL = "https://api.anosys.ai/api/resolveapikeys"


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


def resolve_api_key(api_key: Optional[str] = None, timeout: int = 30) -> str:
    """
    Resolve the API key to get the logging endpoint URL.
    
    Args:
        api_key: AnoSys API key (defaults to ANOSYS_API_KEY env var)
        timeout: Request timeout in seconds
        
    Returns:
        The resolved API URL for logging
    """
    if api_key is None:
        api_key = os.getenv('ANOSYS_API_KEY')
    
    if not api_key:
        print("[ERROR]‼️ ANOSYS_API_KEY not found. Please obtain your API key from "
              "https://console.anosys.ai/collect/integrationoptions")
        return DEFAULT_API_URL
    
    try:
        response = requests.get(
            f"{API_KEY_RESOLVER_URL}?apikey={api_key}",
            timeout=timeout
        )
        response.raise_for_status()
        data = response.json()
        return data.get("url", DEFAULT_API_URL)
    except requests.exceptions.RequestException as e:
        print(f"[ERROR]❌ Failed to resolve API key: {e}")
        return DEFAULT_API_URL


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
