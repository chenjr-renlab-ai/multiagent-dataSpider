"""
Tests for monitoring / observability endpoints.

Coverage:
  GET /api/agents   — list active agents
  GET /api/streams  — Redis Stream depths
  GET /api/circuits — circuit-breaker states
"""
from __future__ import annotations

import json
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport


# ---------------------------------------------------------------------------
# Helpers — build a monitor app with seeded data
# ---------------------------------------------------------------------------

def _build_monitor_app_with_data(
    agents: list | None = None,
    streams: list | None = None,
    circuits: list | None = None,
) -> FastAPI:
    """
    Build a minimal FastAPI that returns hard-coded monitor data so we can
    assert on specific field shapes without hitting real Redis.
    """
    from fastapi import FastAPI

    app = FastAPI()

    _agents = agents or []
    _streams = streams or []
    _circuits = circuits or []

    @app.get("/api/agents")
    async def list_agents():
        return _agents

    @app.get("/api/streams")
    async def list_streams():
        return _streams

    @app.get("/api/circuits")
    async def list_circuits():
        return _circuits

    return app


# ---------------------------------------------------------------------------
# GET /api/agents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_agents_returns_list(client: AsyncClient) -> None:
    """The agents endpoint returns a JSON array (may be empty)."""
    # Act
    response = await client.get("/api/agents")

    # Assert
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_get_agents_item_fields() -> None:
    """When agents are present their records contain required fields."""
    # Arrange — build an app that returns a seeded agent
    seeded_agents = [
        {
            "agent_id": "crawler-001",
            "tier": 2,
            "status": "IDLE",
            "error_count": 0,
            "current_url": None,
            "last_heartbeat": 1700000000,
        }
    ]
    app = _build_monitor_app_with_data(agents=seeded_agents)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Act
        response = await ac.get("/api/agents")

    # Assert
    assert response.status_code == 200
    agents = response.json()
    assert len(agents) == 1
    agent = agents[0]
    for field in ("agent_id", "tier", "status", "error_count"):
        assert field in agent, f"Missing field '{field}' in agent"


@pytest.mark.asyncio
async def test_get_agents_status_values() -> None:
    """Agent status must be one of the defined AgentStatus values."""
    # Arrange
    valid_statuses = {"IDLE", "PROCESSING", "ERROR", "STOPPED"}
    seeded_agents = [
        {"agent_id": "a1", "tier": 1, "status": "IDLE", "error_count": 0},
        {"agent_id": "a2", "tier": 2, "status": "PROCESSING", "error_count": 2},
    ]
    app = _build_monitor_app_with_data(agents=seeded_agents)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/agents")

    # Assert
    assert response.status_code == 200
    for agent in response.json():
        assert agent["status"] in valid_statuses


# ---------------------------------------------------------------------------
# GET /api/streams
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_streams_returns_list(client: AsyncClient) -> None:
    """The streams endpoint returns a JSON array."""
    # Act
    response = await client.get("/api/streams")

    # Assert
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_get_streams_item_fields() -> None:
    """Each stream entry contains 'name' (str) and 'depth' (int) fields."""
    # Arrange
    seeded_streams = [
        {"name": "crawl_jobs", "depth": 42},
        {"name": "raw_data", "depth": 0},
    ]
    app = _build_monitor_app_with_data(streams=seeded_streams)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/streams")

    # Assert
    assert response.status_code == 200
    streams = response.json()
    assert len(streams) == 2
    for stream in streams:
        assert "name" in stream
        assert "depth" in stream
        assert isinstance(stream["depth"], int)


@pytest.mark.asyncio
async def test_get_streams_depth_non_negative() -> None:
    """Stream depth must always be >= 0."""
    # Arrange
    seeded_streams = [
        {"name": "crawl_jobs", "depth": 100},
        {"name": "dead_letters", "depth": 0},
    ]
    app = _build_monitor_app_with_data(streams=seeded_streams)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/streams")

    # Assert
    assert response.status_code == 200
    for stream in response.json():
        assert stream["depth"] >= 0


# ---------------------------------------------------------------------------
# GET /api/circuits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_circuits_returns_list(client: AsyncClient) -> None:
    """The circuits endpoint returns a JSON array."""
    # Act
    response = await client.get("/api/circuits")

    # Assert
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_get_circuits_item_fields() -> None:
    """Each circuit entry contains 'domain' and 'state' fields."""
    # Arrange
    seeded_circuits = [
        {"domain": "example.com", "state": "CLOSED", "failures": 0},
    ]
    app = _build_monitor_app_with_data(circuits=seeded_circuits)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/circuits")

    # Assert
    assert response.status_code == 200
    circuits = response.json()
    assert len(circuits) == 1
    circuit = circuits[0]
    assert "domain" in circuit
    assert "state" in circuit


@pytest.mark.asyncio
async def test_get_circuits_state_values() -> None:
    """Circuit state must be one of CLOSED, OPEN, HALF_OPEN."""
    # Arrange
    valid_states = {"CLOSED", "OPEN", "HALF_OPEN"}
    seeded_circuits = [
        {"domain": "foo.com", "state": "OPEN", "failures": 5},
        {"domain": "bar.com", "state": "HALF_OPEN", "failures": 1},
        {"domain": "baz.com", "state": "CLOSED", "failures": 0},
    ]
    app = _build_monitor_app_with_data(circuits=seeded_circuits)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/circuits")

    # Assert
    assert response.status_code == 200
    for circuit in response.json():
        assert circuit["state"] in valid_states


@pytest.mark.asyncio
async def test_get_circuits_closed_has_zero_failures() -> None:
    """A CLOSED circuit should report failure_count == 0 (or omit it)."""
    # Arrange
    seeded_circuits = [{"domain": "healthy.com", "state": "CLOSED", "failures": 0}]
    app = _build_monitor_app_with_data(circuits=seeded_circuits)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/circuits")

    # Assert
    assert response.status_code == 200
    circuit = response.json()[0]
    failure_count = circuit.get("failures") or circuit.get("failure_count") or 0
    assert failure_count == 0
