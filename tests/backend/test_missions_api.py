"""
Tests for Mission CRUD endpoints.

Coverage:
  POST   /api/missions  — create (success, missing name, empty targets, invalid url)
  GET    /api/missions  — list (shape, pagination)
  GET    /api/missions/{id}  — detail / 404
  DELETE /api/missions/{id}  — cancel / 404 / 409
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from _constants import MISSION_ID, MISSION_ID_COMPLETED

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_PAYLOAD = {
    "name": "test",
    "targets": [
        {
            "url": "https://example.com",
            "type": "api",
            "extract": {
                "type": "json_path",
                "rules": {"title": "$.title"},
            },
        }
    ],
    "schedule": {"type": "once"},
}


# ---------------------------------------------------------------------------
# POST /api/missions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_mission_success(client: AsyncClient) -> None:
    """Creating a mission with a valid payload returns 201 and a mission object."""
    # Arrange — valid payload defined above

    # Act
    response = await client.post("/api/missions", json=VALID_PAYLOAD)

    # Assert
    assert response.status_code == 201, response.text
    body = response.json()
    assert "id" in body
    assert body["name"] == "test"
    assert body["status"] == "pending"
    assert "created_at" in body
    assert "job_total" in body
    assert "job_done" in body
    assert "job_failed" in body


@pytest.mark.asyncio
async def test_create_mission_response_fields(client: AsyncClient) -> None:
    """The 201 response body must contain all required mission fields."""
    # Act
    response = await client.post("/api/missions", json=VALID_PAYLOAD)

    # Assert
    assert response.status_code == 201
    body = response.json()
    required_fields = ("id", "name", "status", "created_at", "job_total", "job_done", "job_failed")
    for field in required_fields:
        assert field in body, f"Missing required field: {field}"


@pytest.mark.asyncio
async def test_create_mission_missing_name(client: AsyncClient) -> None:
    """Omitting the required 'name' field must return HTTP 422 Unprocessable Entity."""
    # Arrange — payload without 'name'
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "name"}

    # Act
    response = await client.post("/api/missions", json=payload)

    # Assert
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_mission_empty_targets(client: AsyncClient) -> None:
    """An empty targets list violates the min_length=1 constraint and returns 422."""
    # Arrange
    payload = {**VALID_PAYLOAD, "targets": []}

    # Act
    response = await client.post("/api/missions", json=payload)

    # Assert
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_mission_invalid_url(client: AsyncClient) -> None:
    """A target with a non-HTTP/HTTPS URL (e.g. 'not-a-url') returns 422."""
    # Arrange
    payload = {
        **VALID_PAYLOAD,
        "targets": [
            {
                "url": "not-a-url-at-all",
                "type": "api",
                "extract": {"type": "json_path", "rules": {}},
            }
        ],
    }

    # Act
    response = await client.post("/api/missions", json=payload)

    # Assert
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/missions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_missions_empty(client: AsyncClient) -> None:
    """The list endpoint returns a response that contains an 'items' list."""
    # Act
    response = await client.get("/api/missions")

    # Assert
    assert response.status_code == 200
    body = response.json()
    # The test app returns {"items": [...], "total": N, ...}
    # Accept both bare list and envelope shapes for robustness.
    if isinstance(body, list):
        assert isinstance(body, list)
    else:
        assert "items" in body
        assert isinstance(body["items"], list)


@pytest.mark.asyncio
async def test_list_missions_pagination(client: AsyncClient) -> None:
    """The ?page and ?limit query parameters are accepted and respected."""
    # Act
    response = await client.get("/api/missions?page=1&limit=1")

    # Assert
    assert response.status_code == 200
    body = response.json()
    items = body if isinstance(body, list) else body.get("items", [])
    assert len(items) <= 1


@pytest.mark.asyncio
async def test_list_missions_contains_expected_fields(client: AsyncClient) -> None:
    """Each mission in the list contains at minimum id, name, status, created_at."""
    # Act
    response = await client.get("/api/missions")

    # Assert
    assert response.status_code == 200
    body = response.json()
    items = body if isinstance(body, list) else body.get("items", [])
    assert len(items) >= 1, "Expected at least the seeded missions in the response"
    for mission in items:
        for field in ("id", "name", "status", "created_at"):
            assert field in mission, f"Mission missing field: {field}"


# ---------------------------------------------------------------------------
# GET /api/missions/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_mission_success(client: AsyncClient) -> None:
    """Requesting an existing mission by id returns 200 with the correct object."""
    # Act
    response = await client.get(f"/api/missions/{MISSION_ID}")

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert str(body["id"]) == MISSION_ID


@pytest.mark.asyncio
async def test_get_mission_not_found(client: AsyncClient) -> None:
    """Requesting a non-existent mission id returns HTTP 404."""
    # Arrange
    non_existent = "00000000-0000-0000-0000-000000000000"

    # Act
    response = await client.get(f"/api/missions/{non_existent}")

    # Assert
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/missions/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_mission(client: AsyncClient) -> None:
    """Cancelling a pending mission returns a success status (200 or 204)."""
    # Act
    response = await client.delete(f"/api/missions/{MISSION_ID}")

    # Assert — accept either 200 (with body) or 204 (no body)
    assert response.status_code in (200, 204)
    if response.status_code == 200:
        assert response.json().get("status") == "cancelled"


@pytest.mark.asyncio
async def test_cancel_mission_not_found(client: AsyncClient) -> None:
    """Attempting to cancel a non-existent mission returns HTTP 404."""
    # Arrange
    non_existent = "00000000-0000-0000-0000-000000000001"

    # Act
    response = await client.delete(f"/api/missions/{non_existent}")

    # Assert
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cancel_completed_mission(client: AsyncClient) -> None:
    """Attempting to cancel an already-completed mission returns HTTP 409 Conflict."""
    # Act
    response = await client.delete(f"/api/missions/{MISSION_ID_COMPLETED}")

    # Assert
    assert response.status_code == 409
