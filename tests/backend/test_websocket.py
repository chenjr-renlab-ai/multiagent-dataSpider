"""
Tests for the WebSocket console endpoint: /ws/console

Uses starlette.testclient.TestClient which supports WebSocket connections
without needing a live server.

All tests operate against the test-double FastAPI app (from conftest.py)
so no real Redis or DB connections are made.
"""
from __future__ import annotations

import json

import pytest

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ws_connect(test_app) -> None:
    """
    Connecting to /ws/console must succeed (101 Switching Protocols) and
    the server must immediately send a message after handshake.
    """
    # Arrange
    from starlette.testclient import TestClient

    client = TestClient(test_app)

    # Act
    with client.websocket_connect("/ws/console") as ws:
        raw = ws.receive_text()

    # Assert — a message was received
    assert raw is not None
    msg = json.loads(raw)
    assert "type" in msg


@pytest.mark.asyncio
async def test_ws_snapshot_format(test_app) -> None:
    """
    The first message after connecting must be a 'snapshot' with the
    required top-level keys: type, ts, data.
    data must contain: agents, streams, circuits, missions.
    """
    # Arrange
    from starlette.testclient import TestClient

    client = TestClient(test_app)

    # Act
    with client.websocket_connect("/ws/console") as ws:
        raw = ws.receive_text()

    # Assert
    msg = json.loads(raw)
    assert msg["type"] == "snapshot"
    assert "ts" in msg
    assert isinstance(msg["ts"], int)
    assert msg["ts"] > 0

    data = msg.get("data", {})
    for key in ("agents", "streams", "circuits", "missions"):
        assert key in data, f"Missing key '{key}' in snapshot data"
    assert isinstance(data["agents"], list)
    assert isinstance(data["streams"], list)
    assert isinstance(data["circuits"], list)
    assert isinstance(data["missions"], list)


@pytest.mark.asyncio
async def test_ws_snapshot_contains_seeded_missions(test_app) -> None:
    """
    The snapshot missions list must contain the missions seeded in the
    test-double store.
    """
    # Arrange
    from starlette.testclient import TestClient
    from _constants import MISSION_ID

    client = TestClient(test_app)

    # Act
    with client.websocket_connect("/ws/console") as ws:
        raw = ws.receive_text()

    # Assert
    msg = json.loads(raw)
    missions = msg["data"]["missions"]
    mission_ids = [str(m["id"]) for m in missions]
    assert MISSION_ID in mission_ids


@pytest.mark.asyncio
async def test_ws_reconnect(test_app) -> None:
    """
    After a WebSocket connection closes a subsequent connection must also
    receive a valid snapshot — reconnect behaviour works correctly.
    """
    # Arrange
    from starlette.testclient import TestClient

    client = TestClient(test_app)

    # Act — first connection
    with client.websocket_connect("/ws/console") as ws:
        first_msg = json.loads(ws.receive_text())

    # Act — second connection (reconnect)
    with client.websocket_connect("/ws/console") as ws:
        second_msg = json.loads(ws.receive_text())

    # Assert — both yield a snapshot
    assert first_msg["type"] == "snapshot"
    assert second_msg["type"] == "snapshot"


@pytest.mark.asyncio
async def test_ws_ping_pong(test_app) -> None:
    """
    Sending the text 'ping' to the server should result in a 'pong' message.
    """
    # Arrange
    from starlette.testclient import TestClient

    client = TestClient(test_app)

    # Act
    with client.websocket_connect("/ws/console") as ws:
        ws.receive_text()  # consume initial snapshot
        ws.send_text("ping")
        pong_raw = ws.receive_text()

    # Assert
    pong = json.loads(pong_raw)
    assert pong["type"] == "pong"
    assert "ts" in pong


@pytest.mark.asyncio
async def test_ws_multiple_clients(test_app) -> None:
    """
    Two simultaneous connections must each receive an independent snapshot
    without interfering with each other.
    """
    # Arrange
    from starlette.testclient import TestClient

    client = TestClient(test_app)

    # Act
    with client.websocket_connect("/ws/console") as ws1:
        with client.websocket_connect("/ws/console") as ws2:
            msg1 = json.loads(ws1.receive_text())
            msg2 = json.loads(ws2.receive_text())

    # Assert
    assert msg1["type"] == "snapshot"
    assert msg2["type"] == "snapshot"
    assert "data" in msg1
    assert "data" in msg2
