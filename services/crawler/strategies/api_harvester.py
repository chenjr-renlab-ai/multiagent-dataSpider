"""
API Harvester strategy: performs async HTTP requests using httpx.
Handles JSON/XML APIs with authentication headers.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0
DEFAULT_HEADERS = {
    "User-Agent": "MultiAgent-DataSpider/1.0",
    "Accept": "application/json, */*",
}


class ApiHarvester:
    """
    Stateless harvester for API endpoints.
    Returns raw text content for the processor to parse.
    """

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = 3,
    ) -> None:
        self.timeout = timeout
        self.max_retries = max_retries

    async def fetch(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[dict[str, str]] = None,
        body: Optional[dict[str, Any]] = None,
        retry_count: int = 0,
    ) -> tuple[str, int, dict[str, str]]:
        """
        Perform the HTTP request.

        Returns:
            (response_text, status_code, response_headers)

        Raises:
            httpx.HTTPStatusError for 4xx/5xx after retries
            httpx.RequestError for connection-level errors
        """
        merged_headers = {**DEFAULT_HEADERS, **(headers or {})}

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            for attempt in range(max(1, self.max_retries - retry_count)):
                try:
                    if method.upper() in ("POST", "PUT", "PATCH"):
                        response = await client.request(
                            method,
                            url,
                            headers=merged_headers,
                            json=body,
                        )
                    else:
                        response = await client.request(
                            method,
                            url,
                            headers=merged_headers,
                        )

                    # Raise for 4xx/5xx
                    response.raise_for_status()
                    logger.debug("API %s %s -> %d", method, url, response.status_code)
                    return response.text, response.status_code, dict(response.headers)

                except httpx.HTTPStatusError as exc:
                    status = exc.response.status_code
                    logger.warning(
                        "HTTP %d for %s (attempt %d)", status, url, attempt + 1
                    )
                    if status in (429, 503):
                        # Rate limit / unavailable: propagate for circuit breaker
                        raise
                    if attempt == max(1, self.max_retries - retry_count) - 1:
                        raise
                    # Brief back-off
                    import asyncio
                    await asyncio.sleep(2 ** attempt)

                except httpx.RequestError as exc:
                    logger.warning("Request error for %s: %s (attempt %d)", url, exc, attempt + 1)
                    if attempt == max(1, self.max_retries - retry_count) - 1:
                        raise
                    import asyncio
                    await asyncio.sleep(2 ** attempt)

        raise RuntimeError(f"All retries exhausted for {url}")

    @staticmethod
    def extract_domain(url: str) -> str:
        return urlparse(url).netloc
