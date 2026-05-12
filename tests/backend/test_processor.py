"""
Unit tests for Tier-3 Processor logic.

Covers:
  - JSONPathExtractor  — json_path rule evaluation
  - CSSExtractor       — CSS selector extraction (HTML)
  - Deduplicator       — content-hash-based dedup
  - Normalizer         — field normalisation (strip, lowercase, numeric cast)

Reference implementations are defined inline so the suite is runnable
immediately.  Replace with real imports once services/processor/ exists.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Reference implementations
# ---------------------------------------------------------------------------


class JSONPathExtractor:
    """
    Minimal JSONPath evaluator that supports dot-notation paths like
    $.title, $.data.price, $.items[0].name.

    Only a subset of JSONPath is implemented — sufficient for the spec.
    """

    @staticmethod
    def _resolve(data: Any, path: str) -> Any:
        """Resolve a single JSONPath expression against *data*."""
        if not path.startswith("$"):
            raise ValueError(f"JSONPath must start with '$', got: {path!r}")
        parts = re.split(r"[.\[\]]+", path.lstrip("$").lstrip("."))
        node = data
        for part in parts:
            if not part:
                continue
            if isinstance(node, dict):
                node = node.get(part)
            elif isinstance(node, list):
                try:
                    node = node[int(part)]
                except (IndexError, ValueError):
                    return None
            else:
                return None
        return node

    def extract(self, data: Any, rules: dict[str, str]) -> dict[str, Any]:
        """
        Apply each rule (field → json_path) and return a dict of
        {field: extracted_value}.
        """
        return {field: self._resolve(data, path) for field, path in rules.items()}


class CSSExtractor:
    """Extract fields from HTML using CSS selectors."""

    def extract(self, html: str, rules: dict[str, str]) -> dict[str, Any]:
        """Return {field: text_or_None} for each CSS selector rule."""
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

        # Fallback: return None for all fields
        return {field: None for field in rules}


class Deduplicator:
    """
    Content-hash-based deduplication.

    A seen-set stores SHA-256 digests of serialised extracted_fields
    dicts.  is_duplicate() returns True if the content was seen before.
    """

    def __init__(self):
        self._seen: set[str] = set()

    @staticmethod
    def _hash(fields: dict) -> str:
        payload = json.dumps(fields, sort_keys=True).encode()
        return hashlib.sha256(payload).hexdigest()

    def is_duplicate(self, fields: dict) -> bool:
        """Return True if this exact field set was already processed."""
        digest = self._hash(fields)
        if digest in self._seen:
            return True
        self._seen.add(digest)
        return False

    def reset(self) -> None:
        """Clear the seen-set (e.g., between missions)."""
        self._seen.clear()


class Normalizer:
    """
    Normalise extracted string fields:
      - Strip leading/trailing whitespace
      - Attempt numeric cast for fields whose values look like numbers
      - Optional lowercase flag
    """

    def normalize(
        self,
        fields: dict[str, Any],
        lowercase: bool = False,
    ) -> dict[str, Any]:
        """Return a new dict with normalised values."""
        result = {}
        for key, value in fields.items():
            if isinstance(value, str):
                value = value.strip()
                # Numeric cast
                try:
                    value = int(value)
                except ValueError:
                    try:
                        value = float(value)
                    except ValueError:
                        if lowercase:
                            value = value.lower()
            result[key] = value
        return result


# ---------------------------------------------------------------------------
# JSONPathExtractor tests
# ---------------------------------------------------------------------------


def test_jsonpath_simple_field() -> None:
    """Extracting a top-level field with $.field returns its value."""
    # Arrange
    data = {"title": "Hello World", "count": 42}
    extractor = JSONPathExtractor()

    # Act
    result = extractor.extract(data, {"title": "$.title"})

    # Assert
    assert result == {"title": "Hello World"}


def test_jsonpath_nested_field() -> None:
    """Dot-notation paths resolve nested keys correctly."""
    # Arrange
    data = {"meta": {"price": 9.99, "currency": "USD"}}
    extractor = JSONPathExtractor()

    # Act
    result = extractor.extract(data, {"price": "$.meta.price", "currency": "$.meta.currency"})

    # Assert
    assert result["price"] == 9.99
    assert result["currency"] == "USD"


def test_jsonpath_array_index() -> None:
    """Bracket-index notation resolves array elements."""
    # Arrange
    data = {"items": [{"name": "first"}, {"name": "second"}]}
    extractor = JSONPathExtractor()

    # Act
    result = extractor.extract(data, {"first_item": "$.items[0].name"})

    # Assert
    assert result["first_item"] == "first"


def test_jsonpath_missing_key_returns_none() -> None:
    """A path that does not exist in the data must return None."""
    # Arrange
    data = {"x": 1}
    extractor = JSONPathExtractor()

    # Act
    result = extractor.extract(data, {"missing": "$.y.z"})

    # Assert
    assert result["missing"] is None


def test_jsonpath_multiple_rules() -> None:
    """All rules are applied independently in a single extract() call."""
    # Arrange
    data = {"a": 1, "b": 2, "c": 3}
    extractor = JSONPathExtractor()
    rules = {"field_a": "$.a", "field_b": "$.b", "field_c": "$.c"}

    # Act
    result = extractor.extract(data, rules)

    # Assert
    assert result == {"field_a": 1, "field_b": 2, "field_c": 3}


# ---------------------------------------------------------------------------
# CSSExtractor tests
# ---------------------------------------------------------------------------


def test_css_extractor_basic() -> None:
    """CSS extractor returns text for matched elements."""
    # Arrange
    html = "<html><body><h1 class='title'>My Title</h1></body></html>"
    extractor = CSSExtractor()

    # Act
    result = extractor.extract(html, {"title": "h1.title"})

    # Assert
    assert result.get("title") == "My Title"


def test_css_extractor_missing_selector() -> None:
    """When a CSS selector matches nothing the field value must be None."""
    # Arrange
    html = "<html><body><p>No match here</p></body></html>"
    extractor = CSSExtractor()

    # Act
    result = extractor.extract(html, {"ghost": "span.nonexistent"})

    # Assert
    assert result.get("ghost") is None


def test_css_extractor_multiple_rules() -> None:
    """Multiple CSS rules are extracted in one pass."""
    # Arrange
    html = """
    <html><body>
      <span class="author">Alice</span>
      <span class="date">2026-05-12</span>
    </body></html>
    """
    extractor = CSSExtractor()

    # Act
    result = extractor.extract(html, {"author": "span.author", "date": "span.date"})

    # Assert
    assert result.get("author") == "Alice"
    assert result.get("date") == "2026-05-12"


# ---------------------------------------------------------------------------
# Deduplicator tests
# ---------------------------------------------------------------------------


def test_deduplicator_first_item_not_duplicate() -> None:
    """The first time a field-set is seen, is_duplicate() returns False."""
    # Arrange
    dedup = Deduplicator()
    fields = {"title": "Hello", "price": 9.99}

    # Act / Assert
    assert dedup.is_duplicate(fields) is False


def test_deduplicator_second_identical_is_duplicate() -> None:
    """Passing the same field-set twice must return True on the second call."""
    # Arrange
    dedup = Deduplicator()
    fields = {"title": "Duplicate", "price": 1.0}
    dedup.is_duplicate(fields)  # first call

    # Act
    result = dedup.is_duplicate(fields)

    # Assert
    assert result is True


def test_deduplicator_different_values_not_duplicate() -> None:
    """Two distinct field-sets must both return False."""
    # Arrange
    dedup = Deduplicator()

    # Act / Assert
    assert dedup.is_duplicate({"title": "A"}) is False
    assert dedup.is_duplicate({"title": "B"}) is False


def test_deduplicator_order_of_keys_ignored() -> None:
    """
    Deduplication is based on content, not key insertion order;
    two dicts with the same pairs in different order are duplicates.
    """
    # Arrange
    dedup = Deduplicator()
    fields_a = {"b": 2, "a": 1}
    fields_b = {"a": 1, "b": 2}
    dedup.is_duplicate(fields_a)

    # Act
    result = dedup.is_duplicate(fields_b)

    # Assert
    assert result is True


def test_deduplicator_reset_clears_state() -> None:
    """After reset(), previously seen items are no longer considered duplicates."""
    # Arrange
    dedup = Deduplicator()
    fields = {"x": 42}
    dedup.is_duplicate(fields)  # mark as seen
    dedup.reset()

    # Act
    result = dedup.is_duplicate(fields)

    # Assert
    assert result is False


# ---------------------------------------------------------------------------
# Normalizer tests
# ---------------------------------------------------------------------------


def test_normalizer_strips_whitespace() -> None:
    """String values with leading/trailing whitespace are stripped."""
    # Arrange
    normalizer = Normalizer()
    fields = {"name": "  Alice  ", "city": "\tParis\n"}

    # Act
    result = normalizer.normalize(fields)

    # Assert
    assert result["name"] == "Alice"
    assert result["city"] == "Paris"


def test_normalizer_casts_integers() -> None:
    """String values that look like integers are cast to int."""
    # Arrange
    normalizer = Normalizer()
    fields = {"count": "42"}

    # Act
    result = normalizer.normalize(fields)

    # Assert
    assert result["count"] == 42
    assert isinstance(result["count"], int)


def test_normalizer_casts_floats() -> None:
    """String values that look like floats are cast to float."""
    # Arrange
    normalizer = Normalizer()
    fields = {"price": "9.99"}

    # Act
    result = normalizer.normalize(fields)

    # Assert
    assert result["price"] == pytest.approx(9.99)
    assert isinstance(result["price"], float)


def test_normalizer_lowercase_flag() -> None:
    """With lowercase=True non-numeric strings are lowercased."""
    # Arrange
    normalizer = Normalizer()
    fields = {"category": "Electronics", "brand": "SONY"}

    # Act
    result = normalizer.normalize(fields, lowercase=True)

    # Assert
    assert result["category"] == "electronics"
    assert result["brand"] == "sony"


def test_normalizer_preserves_non_string_types() -> None:
    """Numeric fields already stored as int/float are passed through unchanged."""
    # Arrange
    normalizer = Normalizer()
    fields = {"count": 7, "ratio": 0.5, "flag": True}

    # Act
    result = normalizer.normalize(fields)

    # Assert
    assert result["count"] == 7
    assert result["ratio"] == pytest.approx(0.5)
    assert result["flag"] is True
