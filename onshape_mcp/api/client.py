"""Onshape API client for REST API communication."""

import base64
import os
import time
import httpx
from typing import Any, Dict, Optional
from pydantic import BaseModel
from loguru import logger

ONSHAPE_TOKEN_URL = "https://oauth.onshape.com/oauth/token"


class OnshapeCredentials(BaseModel):
    """Onshape API credentials.

    Supports two auth modes:
    1. API Keys (Basic Auth): set access_key + secret_key
    2. OAuth Bearer Token: set oauth_token (access_key/secret_key ignored)
       With auto-refresh: also set oauth_client_id, oauth_client_secret, oauth_refresh_token
    """

    access_key: str = ""
    secret_key: str = ""
    oauth_token: str = ""
    oauth_client_id: str = ""
    oauth_client_secret: str = ""
    oauth_refresh_token: str = ""
    base_url: str = "https://cad.onshape.com"


class OnshapeClient:
    """Client for interacting with Onshape REST API.

    Supports both API Key (Basic Auth) and OAuth (Bearer Token) authentication.

    Use as an async context manager to ensure proper cleanup:
        async with OnshapeClient(credentials) as client:
            result = await client.get("/api/v9/documents")
    """

    def __init__(self, credentials: OnshapeCredentials):
        """Initialize the Onshape client.

        Args:
            credentials: Onshape API credentials (API keys or OAuth token)
        """
        self.credentials = credentials
        self.base_url = credentials.base_url
        self._client: Optional[httpx.AsyncClient] = None
        self._own_client = False
        self._token_expires_at: float = time.time() + 3500 if credentials.oauth_token else 0

    async def __aenter__(self):
        """Async context manager entry."""
        self._client = httpx.AsyncClient(timeout=30.0)
        self._own_client = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - ensures cleanup."""
        await self.close()
        return False

    def _ensure_client(self):
        """Ensure HTTP client is initialized."""
        if self._client is None:
            # Create client if not using context manager (backwards compatibility)
            self._client = httpx.AsyncClient(timeout=30.0)
            self._own_client = True

    def _refresh_oauth_token(self):
        """Refresh OAuth token if it's expired or about to expire."""
        if not self.credentials.oauth_token:
            return
        if not self.credentials.oauth_refresh_token:
            return
        if time.time() < self._token_expires_at - 60:  # 60s buffer
            return

        logger.info("OAuth token expired or expiring soon, refreshing...")
        try:
            response = httpx.post(ONSHAPE_TOKEN_URL, data={
                "grant_type": "refresh_token",
                "refresh_token": self.credentials.oauth_refresh_token,
                "client_id": self.credentials.oauth_client_id,
                "client_secret": self.credentials.oauth_client_secret,
            }, timeout=30.0)
            response.raise_for_status()
            tokens = response.json()
            self.credentials.oauth_token = tokens["access_token"]
            if "refresh_token" in tokens:
                self.credentials.oauth_refresh_token = tokens["refresh_token"]
            self._token_expires_at = time.time() + tokens.get("expires_in", 3500)
            logger.info("OAuth token refreshed successfully")
        except Exception as e:
            logger.error(f"Failed to refresh OAuth token: {e}")

    def _get_auth_header(self) -> str:
        """Generate auth header from credentials.

        Uses OAuth Bearer token if available (with auto-refresh),
        otherwise falls back to Basic Auth (API keys).

        Returns:
            Authorization header value
        """
        if self.credentials.oauth_token:
            self._refresh_oauth_token()
            return f"Bearer {self.credentials.oauth_token}"
        auth_string = f"{self.credentials.access_key}:{self.credentials.secret_key}"
        encoded = base64.b64encode(auth_string.encode()).decode()
        return f"Basic {encoded}"

    def _sanitize_for_logging(self, data: Any, max_length: int = 200) -> str:
        """Sanitize sensitive data for logging.

        Args:
            data: Data to sanitize
            max_length: Maximum length of output string

        Returns:
            Sanitized string safe for logging
        """
        if isinstance(data, dict):
            sanitized = {}
            for k, v in data.items():
                if k.lower() in {
                    "authorization",
                    "api_key",
                    "secret",
                    "password",
                    "token",
                    "access_key",
                    "secret_key",
                }:
                    sanitized[k] = "***REDACTED***"
                else:
                    sanitized[k] = v
            return str(sanitized)[:max_length]

        result = str(data)
        if len(result) > max_length:
            return result[:max_length] + "... (truncated)"
        return result

    async def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make a GET request to Onshape API.

        Args:
            path: API endpoint path (e.g., "/api/v9/documents")
            params: Query parameters

        Returns:
            JSON response data
        """
        url = f"{self.base_url}{path}"
        headers = {
            "Authorization": self._get_auth_header(),
            "Accept": "application/json;charset=UTF-8; qs=0.09",
        }

        self._ensure_client()
        logger.debug(f"GET {url} with params: {self._sanitize_for_logging(params)}")
        response = await self._client.get(url, params=params, headers=headers)
        response.raise_for_status()
        result = response.json()
        logger.debug(f"GET {url} response: {self._sanitize_for_logging(result, max_length=500)}")
        return result

    async def post(
        self,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make a POST request to Onshape API.

        Args:
            path: API endpoint path
            data: JSON body data
            params: Query parameters

        Returns:
            JSON response data
        """
        url = f"{self.base_url}{path}"
        headers = {
            "Authorization": self._get_auth_header(),
            "Accept": "application/json;charset=UTF-8; qs=0.09",
            "Content-Type": "application/json;charset=UTF-8; qs=0.09",
        }

        self._ensure_client()
        logger.debug(f"POST {url} with params: {self._sanitize_for_logging(params)}")
        logger.debug(f"POST {url} data: {self._sanitize_for_logging(data, max_length=1000)}")
        response = await self._client.post(url, json=data, params=params, headers=headers)

        # Log error details if request failed
        if response.status_code >= 400:
            try:
                error_body = response.json()
                logger.error(
                    f"POST {url} failed with status {response.status_code}: {self._sanitize_for_logging(error_body)}"
                )
            except Exception:
                logger.error(
                    f"POST {url} failed with status {response.status_code}: {response.text[:500]}"
                )

        response.raise_for_status()
        result = response.json()
        logger.debug(f"POST {url} response: {self._sanitize_for_logging(result, max_length=500)}")
        return result

    async def delete(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make a DELETE request to Onshape API.

        Args:
            path: API endpoint path
            params: Query parameters

        Returns:
            JSON response data
        """
        url = f"{self.base_url}{path}"
        headers = {
            "Authorization": self._get_auth_header(),
            "Accept": "application/json;charset=UTF-8; qs=0.09",
        }

        self._ensure_client()
        response = await self._client.delete(url, params=params, headers=headers)
        response.raise_for_status()
        return response.json()

    async def close(self):
        """Close the HTTP client and clean up resources."""
        if self._client and self._own_client:
            await self._client.aclose()
            self._client = None
