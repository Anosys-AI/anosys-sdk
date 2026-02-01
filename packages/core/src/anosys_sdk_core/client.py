"""
HTTP client for AnoSys API.

Provides a centralized client for sending data to the AnoSys logging endpoint.
"""

import json
from typing import Any, Dict, Optional

import requests

from anosys_sdk_core.config import resolve_api_key


class AnosysClient:
    """
    HTTP client for sending data to AnoSys API.
    
    Attributes:
        api_url: The resolved API endpoint URL
        timeout: Request timeout in seconds
    """
    
    def __init__(
        self,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: int = 5
    ):
        """
        Initialize the AnoSys client.
        
        Args:
            api_url: Override URL (skips API key resolution if provided)
            api_key: AnoSys API key (defaults to ANOSYS_API_KEY env var)
            timeout: Request timeout in seconds
        """
        if api_url:
            self.api_url = api_url
        else:
            self.api_url = resolve_api_key(api_key)
        self.timeout = timeout
    
    def send(self, data: Dict[str, Any]) -> Optional[requests.Response]:
        """
        Send data to the AnoSys API.
        
        Args:
            data: Dictionary of data to send
            
        Returns:
            Response object on success, None on failure
        """
        try:
            response = requests.post(
                self.api_url,
                json=data,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            print(f"[ANOSYS]❌ POST failed: {e}")
            try:
                print(f"[ANOSYS]❌ Data: {json.dumps(data, indent=2)}")
            except Exception:
                pass
            return None
    
    def send_batch(self, items: list) -> list:
        """
        Send multiple items to the AnoSys API.
        
        Args:
            items: List of data dictionaries to send
            
        Returns:
            List of response objects (None for failures)
        """
        return [self.send(item) for item in items]
