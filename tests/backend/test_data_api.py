"""
Tests for the scraped-data query endpoint.

Coverage:
  GET /api/data?mission_id={id}&page=1&limit=20
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from _constants import MISSION_ID


# ---------------------------------------------------------------------------
# GET /api/data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_data_success(client: AsyncClient) -> None:
    """Querying data for an existing mission returns 200 and a paginated envelope."""
    # Arrange
    params = {"mission_id": MISSION_ID, "page": 1, "limit": 20}

    # Act
    response = await client.get("/api/data", params=params)

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert "total" in body
    assert isinstance(body["items"], list)
    assert isinstance(body["total"], int)


@pytest.mark.asyncio
async def test_get_data_item_fields(client: AsyncClient) -> None:
    """Each data item contains the required ScrapedDataItem fields."""
    # Act
    response = await client.get(
        "/api/data", params={"mission_id": MISSION_ID, "page": 1, "limit": 20}
    )

    # Assert
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) >= 1, "Expected at least one seeded scraped item"
    item = items[0]
    for field in ("id", "target_url", "extracted_fields", "confidence"):
        assert field in item, f"Missing field '{field}' in scraped data item"


@pytest.mark.asyncio
async def test_get_data_confidence_is_float(client: AsyncClient) -> None:
    """The confidence field must be a float in [0, 1]."""
    # Act
    response = await client.get(
        "/api/data", params={"mission_id": MISSION_ID, "page": 1, "limit": 20}
    )

    # Assert
    assert response.status_code == 200
    for item in response.json()["items"]:
        assert isinstance(item["confidence"], (int, float))
        assert 0.0 <= item["confidence"] <= 1.0


@pytest.mark.asyncio
async def test_get_data_extracted_fields_is_dict(client: AsyncClient) -> None:
    """The extracted_fields value must be a JSON object (dict)."""
    # Act
    response = await client.get(
        "/api/data", params={"mission_id": MISSION_ID, "page": 1, "limit": 20}
    )

    # Assert
    assert response.status_code == 200
    for item in response.json()["items"]:
        assert isinstance(item["extracted_fields"], dict)


@pytest.mark.asyncio
async def test_get_data_pagination_params(client: AsyncClient) -> None:
    """page and limit query parameters are forwarded and limit is respected."""
    # Arrange
    params = {"mission_id": MISSION_ID, "page": 1, "limit": 5}

    # Act
    response = await client.get("/api/data", params=params)

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) <= 5


@pytest.mark.asyncio
async def test_get_data_missing_mission_id(client: AsyncClient) -> None:
    """Omitting the required mission_id query parameter returns 422."""
    # Act
    response = await client.get("/api/data")

    # Assert
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_data_envelope_total_non_negative(client: AsyncClient) -> None:
    """The total field in the response envelope must be >= 0."""
    # Act
    response = await client.get(
        "/api/data", params={"mission_id": MISSION_ID, "page": 1, "limit": 20}
    )

    # Assert
    assert response.status_code == 200
    assert response.json()["total"] >= 0


@pytest.mark.asyncio
async def test_get_data_unknown_mission_returns_empty(client: AsyncClient) -> None:
    """A mission_id with no scraped data returns an empty items list."""
    # Arrange
    unknown_id = "ffffffff-ffff-ffff-ffff-ffffffffffff"

    # Act
    response = await client.get("/api/data", params={"mission_id": unknown_id})

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0
