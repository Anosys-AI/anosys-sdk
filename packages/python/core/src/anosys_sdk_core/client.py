"""
HTTP client for AnoSys API.

Provides a centralized client for sending data to the AnoSys logging endpoint.
"""

import logging
from typing import Any, Dict, Optional

import requests

from anosys_sdk_core.config import resolve_api_key
from anosys_sdk_core.capture import APP_METADATA_STRING_COLUMNS, current_app_level, prepare_app_record
from anosys_sdk_core.models import BASE_KEY_MAPPING, DEFAULT_STARTING_INDICES
from anosys_sdk_core.transport import post_record
from anosys_sdk_core.util.batching import reassign

logger = logging.getLogger(__name__)


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
            record = dict(data)
            # If caller passed unmapped logical keys (e.g. "name", "trace_id", "input", "source"),
            # map them to CVS/OTel columns first so metadata allowlisting works as expected.
            already_mapped = any(
                k in APP_METADATA_STRING_COLUMNS or k.startswith(("cvs", "cvn", "cvb", "otel_", "gen_ai_", "llm_"))
                for k in record
            )
            if not already_mapped:
                record = reassign(record, BASE_KEY_MAPPING.copy(), DEFAULT_STARTING_INDICES.copy())
            payload = prepare_app_record(record, current_app_level()[0])
            if payload is None:
                return None  # collection is off
            response = post_record(self.api_url, payload, timeout=self.timeout)
            if response is None:
                return None
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            logger.error("AnoSys POST failed (%s)", type(e).__name__)  # no URL or payload in logs
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
