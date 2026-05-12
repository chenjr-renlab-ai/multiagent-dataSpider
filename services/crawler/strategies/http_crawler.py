"""
HTTP Crawler strategy: fetches HTML pages using httpx.
Uses CSS/XPath selectors to extract structured content.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; MultiAgent-DataSpider/1.0; "
        "+https://github.com/spider)"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}


class HttpCrawler:
    """
    Fetches HTML pages and returns raw HTML content.
    The processor handles CSS/XPath extraction.
    """

    def __init__(self, timeout: float = DEFAULT_TIMEOUT, max_retries: int = 3) -> None:
        self.timeout = timeout
        self.max_retries = max_retries

    async def fetch(
        self,
        url: str,
        headers: Optional[dict[str, str]] = None,
        retry_count: int = 0,
    ) -> tuple[str, int, str]:
        """
        Fetch the URL.

        Returns:
            (html_content, status_code, final_url)
        """
        merged_headers = {**DEFAULT_HEADERS, **(headers or {})}

        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers=merged_headers,
        ) as client:
            for attempt in range(max(1, self.max_retries - retry_count)):
                try:
                    response = await client.get(url)
                    response.raise_for_status()
                    final_url = str(response.url)
                    logger.debug("HTML GET %s -> %d", url, response.status_code)
                    return response.text, response.status_code, final_url

                except httpx.HTTPStatusError as exc:
                    status = exc.response.status_code
                    logger.warning("HTTP %d crawling %s (attempt %d)", status, url, attempt + 1)
                    if status in (429, 503):
                        raise
                    if attempt == max(1, self.max_retries - retry_count) - 1:
                        raise
                    import asyncio
                    await asyncio.sleep(2 ** attempt)

                except httpx.RequestError as exc:
                    logger.warning("Request error crawling %s: %s", url, exc)
                    if attempt == max(1, self.max_retries - retry_count) - 1:
                        raise
                    import asyncio
                    await asyncio.sleep(2 ** attempt)

        raise RuntimeError(f"All retries exhausted for {url}")

    @staticmethod
    def extract_domain(url: str) -> str:
        return urlparse(url).netloc

    @staticmethod
    def extract_links(html: str, base_url: str) -> list[str]:
        """
        Simple regex-based link extractor from HTML.
        Returns list of absolute URLs.
        """
        pattern = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
        links: list[str] = []
        for match in pattern.finditer(html):
            href = match.group(1).strip()
            if href.startswith(("http://", "https://")):
                links.append(href)
            elif href.startswith("/"):
                links.append(urljoin(base_url, href))
        return list(set(links))
