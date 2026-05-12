"""
Unit tests for Tier-2 Crawler strategies.

All HTTP calls are mocked with httpx.  No real network I/O occurs.

Because the real strategy modules (services/crawler/strategies/) do not
yet exist as files, reference implementations are defined inline in this
module.  When the real code is implemented replace the inline classes with
the actual imports, e.g.:
    from services.crawler.strategies.api_harvester import APIHarvester
    from services.crawler.strategies.http_crawler import HTTPCrawler
    from services.crawler.circuit_breaker import CircuitBreaker
"""
from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Reference implementations
# ---------------------------------------------------------------------------


class DeadLetterWriter:
    """Writes failed jobs to the dead_letters Redis stream."""

    def __init__(self, redis):
        self._redis = redis

    async def write(self, job: dict, reason: str) -> None:
        await self._redis.xadd("dead_letters", {**job, "reason": reason})


class APIHarvester:
    """
    Strategy 0 — plain HTTP/JSON API call using httpx.AsyncClient.
    Writes to dead_letters on HTTP >= 400 error.
    """

    def __init__(self, redis, http_client=None):
        self._redis = redis
        self._http = http_client  # injected for testing
        self._dead_letter = DeadLetterWriter(redis)

    async def fetch(self, url: str, method: str = "GET", headers: dict | None = None) -> dict:
        """Return parsed JSON body on success; raise on 4xx/5xx."""
        import httpx

        client = self._http or httpx.AsyncClient()
        response = await client.request(method, url, headers=headers or {})
        if response.status_code >= 400:
            await self._dead_letter.write(
                {"target_url": url, "method": method},
                reason=f"HTTP {response.status_code}",
            )
            response.raise_for_status()
        return response.json()


class HTTPCrawler:
    """
    Strategy 1 — static HTML download with CSS/XPath/regex extraction.
    """

    def __init__(self, redis, http_client=None):
        self._redis = redis
        self._http = http_client

    async def fetch_html(self, url: str) -> str:
        """Return raw HTML string."""
        import httpx

        client = self._http or httpx.AsyncClient()
        response = await client.get(url)
        response.raise_for_status()
        return response.text

    def extract_css(self, html: str, rules: dict[str, str]) -> dict[str, Any]:
        """
        Extract fields from HTML using CSS selectors.
        Requires 'selectolax' or 'beautifulsoup4'; falls back to a regex
        stub when neither is installed.
        """
        try:
            from selectolax.parser import HTMLParser

            parser = HTMLParser(html)
            result = {}
            for field, selector in rules.items():
                node = parser.css_first(selector)
                result[field] = node.text(strip=True) if node else None
            return result
        except ImportError:
            pass

        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")
            result = {}
            for field, selector in rules.items():
                node = soup.select_one(selector)
                result[field] = node.get_text(strip=True) if node else None
            return result
        except ImportError:
            pass

        # Minimal fallback: return None for every field
        return {field: None for field in rules}


class CircuitBreaker:
    """
    Per-domain circuit breaker.

    States:
      CLOSED   — normal operation
      OPEN     — all calls rejected for `recovery_timeout` seconds
      HALF_OPEN — single probe call allowed after recovery_timeout
    """

    FAILURE_THRESHOLD = 5
    RECOVERY_TIMEOUT = 300  # seconds

    def __init__(self, domain: str):
        self.domain = domain
        self.state = "CLOSED"
        self.failure_count = 0
        self._opened_at: float | None = None

    def record_success(self) -> None:
        """Reset failure count and close the circuit."""
        self.failure_count = 0
        self.state = "CLOSED"
        self._opened_at = None

    def record_failure(self) -> None:
        """Increment failure counter; open the circuit when threshold reached."""
        self.failure_count += 1
        if self.failure_count >= self.FAILURE_THRESHOLD:
            self.state = "OPEN"
            self._opened_at = time.monotonic()

    def allow_request(self) -> bool:
        """Return True if a request may proceed."""
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            elapsed = time.monotonic() - (self._opened_at or 0)
            if elapsed >= self.RECOVERY_TIMEOUT:
                self.state = "HALF_OPEN"
                return True
            return False
        # HALF_OPEN — allow one probe
        return True


# ---------------------------------------------------------------------------
# APIHarvester tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_harvester_get_success(mock_redis: AsyncMock) -> None:
    """
    When the remote API returns 200, APIHarvester.fetch() should return
    the parsed JSON body and NOT write to dead_letters.
    """
    # Arrange
    import httpx

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"title": "Hello World"}
    mock_response.raise_for_status = MagicMock()

    mock_http = AsyncMock()
    mock_http.request = AsyncMock(return_value=mock_response)

    harvester = APIHarvester(mock_redis, http_client=mock_http)

    # Act
    result = await harvester.fetch("https://api.example.com/data")

    # Assert
    assert result == {"title": "Hello World"}
    mock_redis.xadd.assert_not_awaited()  # dead_letters not touched


@pytest.mark.asyncio
async def test_api_harvester_get_failure(mock_redis: AsyncMock) -> None:
    """
    When the remote API returns 500, APIHarvester.fetch() should write
    the failed job to the dead_letters stream and then raise HTTPStatusError.
    """
    # Arrange
    import httpx

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 500

    def raise_for_status():
        raise httpx.HTTPStatusError(
            "Server Error",
            request=MagicMock(),
            response=mock_response,
        )

    mock_response.raise_for_status = raise_for_status

    mock_http = AsyncMock()
    mock_http.request = AsyncMock(return_value=mock_response)
    mock_redis.xadd = AsyncMock(return_value=b"1-0")

    harvester = APIHarvester(mock_redis, http_client=mock_http)

    # Act & Assert
    with pytest.raises(httpx.HTTPStatusError):
        await harvester.fetch("https://api.example.com/broken")

    # dead_letters must have been written
    mock_redis.xadd.assert_awaited_once()
    stream_name = mock_redis.xadd.call_args[0][0]
    assert stream_name == "dead_letters"


@pytest.mark.asyncio
async def test_api_harvester_dead_letter_contains_url(mock_redis: AsyncMock) -> None:
    """
    The dead_letter entry written on failure must include the target URL.
    """
    # Arrange
    import httpx

    target_url = "https://api.example.com/error"
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 503

    def raise_for_status():
        raise httpx.HTTPStatusError("Error", request=MagicMock(), response=mock_response)

    mock_response.raise_for_status = raise_for_status
    mock_http = AsyncMock()
    mock_http.request = AsyncMock(return_value=mock_response)
    mock_redis.xadd = AsyncMock(return_value=b"1-0")

    harvester = APIHarvester(mock_redis, http_client=mock_http)

    # Act
    with pytest.raises(httpx.HTTPStatusError):
        await harvester.fetch(target_url)

    # Assert
    payload = mock_redis.xadd.call_args[0][1]
    assert payload.get("target_url") == target_url


# ---------------------------------------------------------------------------
# HTTPCrawler / CSS extraction tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_crawler_extracts_css(mock_redis: AsyncMock) -> None:
    """
    HTTPCrawler.extract_css() should return the correct text for each
    CSS selector rule applied to the provided HTML.
    """
    # Arrange
    html = """
    <html>
      <head><title>Test Page</title></head>
      <body>
        <h1 class="headline">Breaking News</h1>
        <p class="author">Jane Doe</p>
      </body>
    </html>
    """
    rules = {
        "headline": "h1.headline",
        "author": "p.author",
        "missing": "span.nope",
    }
    crawler = HTTPCrawler(mock_redis)

    # Act
    extracted = crawler.extract_css(html, rules)

    # Assert
    assert extracted.get("headline") == "Breaking News"
    assert extracted.get("author") == "Jane Doe"
    assert extracted.get("missing") is None  # selector not found → None


@pytest.mark.asyncio
async def test_http_crawler_fetch_html_calls_http(mock_redis: AsyncMock) -> None:
    """
    fetch_html() must issue a GET request and return the response body
    as a plain string.
    """
    # Arrange
    import httpx

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.text = "<html><body>hello</body></html>"
    mock_response.raise_for_status = MagicMock()

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_response)

    crawler = HTTPCrawler(mock_redis, http_client=mock_http)

    # Act
    html = await crawler.fetch_html("https://example.com/page")

    # Assert
    assert html == "<html><body>hello</body></html>"
    mock_http.get.assert_awaited_once_with("https://example.com/page")


# ---------------------------------------------------------------------------
# CircuitBreaker tests
# ---------------------------------------------------------------------------


def test_circuit_breaker_starts_closed() -> None:
    """A newly created CircuitBreaker must start in CLOSED state."""
    # Arrange / Act
    cb = CircuitBreaker("example.com")

    # Assert
    assert cb.state == "CLOSED"
    assert cb.failure_count == 0
    assert cb.allow_request() is True


def test_circuit_breaker_opens(mock_redis: AsyncMock) -> None:
    """
    After FAILURE_THRESHOLD consecutive failures the circuit must
    transition to OPEN state and reject further requests.
    """
    # Arrange
    cb = CircuitBreaker("example.com")

    # Act — record exactly FAILURE_THRESHOLD failures
    for _ in range(CircuitBreaker.FAILURE_THRESHOLD):
        cb.record_failure()

    # Assert
    assert cb.state == "OPEN"
    assert cb.allow_request() is False


def test_circuit_breaker_does_not_open_before_threshold() -> None:
    """
    Fewer than FAILURE_THRESHOLD failures must leave the circuit CLOSED.
    """
    # Arrange
    cb = CircuitBreaker("example.com")

    # Act
    for _ in range(CircuitBreaker.FAILURE_THRESHOLD - 1):
        cb.record_failure()

    # Assert
    assert cb.state == "CLOSED"
    assert cb.allow_request() is True


def test_circuit_breaker_half_open() -> None:
    """
    After RECOVERY_TIMEOUT seconds in OPEN state, allow_request() must
    return True and the circuit must transition to HALF_OPEN.
    """
    # Arrange
    cb = CircuitBreaker("slow-site.com")
    for _ in range(CircuitBreaker.FAILURE_THRESHOLD):
        cb.record_failure()
    assert cb.state == "OPEN"

    # Simulate time passing by backdating _opened_at
    cb._opened_at = time.monotonic() - CircuitBreaker.RECOVERY_TIMEOUT - 1

    # Act
    allowed = cb.allow_request()

    # Assert
    assert allowed is True
    assert cb.state == "HALF_OPEN"


def test_circuit_breaker_closes_on_success_after_half_open() -> None:
    """
    A successful probe in HALF_OPEN state should close the circuit and
    reset the failure count.
    """
    # Arrange
    cb = CircuitBreaker("slow-site.com")
    for _ in range(CircuitBreaker.FAILURE_THRESHOLD):
        cb.record_failure()
    cb._opened_at = time.monotonic() - CircuitBreaker.RECOVERY_TIMEOUT - 1
    cb.allow_request()  # transition to HALF_OPEN
    assert cb.state == "HALF_OPEN"

    # Act
    cb.record_success()

    # Assert
    assert cb.state == "CLOSED"
    assert cb.failure_count == 0


def test_circuit_breaker_stays_open_within_timeout() -> None:
    """
    While still within the RECOVERY_TIMEOUT window the circuit must
    remain OPEN and reject all requests.
    """
    # Arrange
    cb = CircuitBreaker("strict.com")
    for _ in range(CircuitBreaker.FAILURE_THRESHOLD):
        cb.record_failure()

    # _opened_at is recent (just now), so we're still inside the timeout
    # Act
    allowed = cb.allow_request()

    # Assert
    assert cb.state == "OPEN"
    assert allowed is False
