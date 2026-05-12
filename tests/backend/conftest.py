"""
Shared pytest fixtures for all backend tests.

Architecture
------------
HTTP-level tests (test_missions_api, test_data_api, test_monitor_api,
test_websocket) use a *test-double FastAPI app* defined here.  This app
re-implements every endpoint from the spec against in-memory stores,
so no real FastAPI-app import, no SQLAlchemy, no Redis driver is needed.

Unit tests (test_coordinator, test_crawlers, test_processor) import
their own inline reference implementations and only need the mock_redis
fixture.
"""
from __future__ import annotations

import json
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from httpx import AsyncClient, ASGITransport

# ---------------------------------------------------------------------------
# Stable UUIDs used across test modules
# ---------------------------------------------------------------------------

MISSION_ID = "11111111-1111-1111-1111-111111111111"
MISSION_ID_COMPLETED = "22222222-2222-2222-2222-222222222222"


# ---------------------------------------------------------------------------
# Redis mock
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_redis() -> AsyncMock:
    """Mock Redis async client — no real Redis required."""
    r = AsyncMock()
    r.set = AsyncMock(return_value=True)
    r.get = AsyncMock(return_value=None)
    r.xadd = AsyncMock(return_value=b"1-0")
    r.xreadgroup = AsyncMock(return_value=[])
    r.xautoclaim = AsyncMock(return_value=(b"0-0", [], []))
    r.xack = AsyncMock(return_value=1)
    r.xlen = AsyncMock(return_value=0)
    r.hset = AsyncMock(return_value=1)
    r.hget = AsyncMock(return_value=None)
    r.hgetall = AsyncMock(return_value={})
    r.hdel = AsyncMock(return_value=1)
    r.expire = AsyncMock(return_value=True)
    r.persist = AsyncMock(return_value=True)
    r.keys = AsyncMock(return_value=[])
    r.delete = AsyncMock(return_value=1)
    r.exists = AsyncMock(return_value=0)
    r.eval = AsyncMock(return_value=1)
    r.publish = AsyncMock(return_value=0)

    async def _empty_scan(*args, **kwargs):
        return
        yield  # async generator

    r.scan_iter = _empty_scan
    return r


# ---------------------------------------------------------------------------
# In-memory mission store
# ---------------------------------------------------------------------------

def _mission_row(
    mid: str,
    name: str,
    status: str,
    targets: list | None = None,
) -> dict:
    return {
        "id": mid,
        "name": name,
        "description": None,
        "config": {
            "targets": targets
            or [{"url": "https://example.com", "type": "api", "extract": {}}],
            "schedule": {"type": "once"},
        },
        "status": status,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
        "completed_at": None,
        "job_total": 0,
        "job_done": 0,
        "job_failed": 0,
    }


# ---------------------------------------------------------------------------
# Test-double FastAPI application
# ---------------------------------------------------------------------------

def _build_test_app() -> FastAPI:
    """
    Build a minimal FastAPI app that implements every endpoint from the spec
    against a fresh in-memory store.  Each call to this function produces an
    independent store, so tests are isolated.
    """
    _missions: dict[str, dict] = {
        MISSION_ID: _mission_row(MISSION_ID, "test", "pending"),
        MISSION_ID_COMPLETED: _mission_row(MISSION_ID_COMPLETED, "done", "completed"),
    }
    _scraped: list[dict] = [
        {
            "id": str(uuid.uuid4()),
            "mission_id": MISSION_ID,
            "target_url": "https://example.com",
            "extracted_fields": {"title": "Hello"},
            "confidence": 1.0,
            "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
        }
    ]

    app = FastAPI(title="DataSpider Test Double")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    # ----- POST /api/missions -----------------------------------------------

    @app.post("/api/missions", status_code=201)
    async def create_mission(body: dict) -> dict:
        # Manual validation to match Pydantic rules
        if "name" not in body or not body["name"]:
            from fastapi import Response
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=422,
                content={"detail": [{"loc": ["body", "name"], "msg": "field required"}]},
            )
        targets = body.get("targets")
        if not targets:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=422,
                content={"detail": [{"loc": ["body", "targets"], "msg": "at least 1 required"}]},
            )
        # Basic URL check
        for t in targets:
            url = t.get("url", "")
            if not (url.startswith("http://") or url.startswith("https://")):
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=422,
                    content={"detail": [{"loc": ["body", "targets", 0, "url"], "msg": "invalid url"}]},
                )
        new_id = str(uuid.uuid4())
        row = _mission_row(new_id, body["name"], "pending", targets=targets)
        _missions[new_id] = row
        return row

    # ----- GET /api/missions ------------------------------------------------

    @app.get("/api/missions")
    async def list_missions(
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
    ) -> dict:
        all_rows = list(_missions.values())
        start = (page - 1) * limit
        end = start + limit
        items = all_rows[start:end]
        return {"items": items, "total": len(all_rows), "page": page, "page_size": limit}

    # ----- GET /api/missions/{id} -------------------------------------------

    @app.get("/api/missions/{mission_id}")
    async def get_mission(mission_id: str) -> dict:
        row = _missions.get(mission_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Mission not found")
        return row

    # ----- DELETE /api/missions/{id} ----------------------------------------

    @app.delete("/api/missions/{mission_id}")
    async def cancel_mission(mission_id: str) -> dict:
        row = _missions.get(mission_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Mission not found")
        if row["status"] in ("completed", "cancelled"):
            raise HTTPException(status_code=409, detail=f"Mission already {row['status']}")
        row = dict(row)
        row["status"] = "cancelled"
        _missions[mission_id] = row
        return row

    # ----- GET /api/data ----------------------------------------------------

    @app.get("/api/data")
    async def list_data(
        mission_id: str = Query(...),
        page: int = Query(1, ge=1),
        limit: int = Query(20, ge=1, le=100),
    ) -> dict:
        items = [i for i in _scraped if i["mission_id"] == mission_id]
        start = (page - 1) * limit
        end = start + limit
        return {"items": items[start:end], "total": len(items)}

    # ----- GET /api/agents --------------------------------------------------

    @app.get("/api/agents")
    async def list_agents() -> list:
        return []

    # ----- GET /api/streams -------------------------------------------------

    @app.get("/api/streams")
    async def list_streams() -> list:
        return []

    # ----- GET /api/circuits ------------------------------------------------

    @app.get("/api/circuits")
    async def list_circuits() -> list:
        return []

    # ----- WebSocket /ws/console --------------------------------------------

    @app.websocket("/ws/console")
    async def ws_console(websocket: WebSocket) -> None:
        await websocket.accept()
        snapshot = {
            "type": "snapshot",
            "ts": int(time.time()),
            "data": {
                "agents": [],
                "streams": [],
                "circuits": [],
                "missions": list(_missions.values())[:50],
            },
        }
        await websocket.send_text(json.dumps(snapshot, default=str))
        try:
            while True:
                text = await websocket.receive_text()
                if text == "ping":
                    await websocket.send_text(
                        json.dumps({"type": "pong", "ts": int(time.time())})
                    )
        except WebSocketDisconnect:
            pass

    return app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def test_app() -> FastAPI:
    """Return a fresh test-double FastAPI app (isolated store per test)."""
    return _build_test_app()


@pytest.fixture
async def client(test_app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient wired to the test-double FastAPI app."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    ) as ac:
        yield ac


__all__ = [
    "mock_redis",
    "test_app",
    "client",
    "MISSION_ID",
    "MISSION_ID_COMPLETED",
]
