"""
API Gateway – FastAPI application.

Handles:
  - HTTP REST endpoints (missions, data, monitor)
  - WebSocket /ws/console for real-time agent/stream/circuit/mission events
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as aioredis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from shared.db import MissionORM, close_db, init_db, session_factory
from shared.redis_client import (
    close_redis,
    ensure_stream_groups,
    get_all_agents,
    get_all_circuits,
    get_redis,
    get_redis_url,
    get_stream_depths,
)
from api_gateway.routers import data, missions, monitor

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# WebSocket connection manager
# ---------------------------------------------------------------------------

class ConnectionManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)

    async def broadcast(self, message: dict[str, Any]) -> None:
        payload = json.dumps(message, default=str)
        dead: list[WebSocket] = []
        for ws in list(self._connections):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.discard(ws)


manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Background tasks
# ---------------------------------------------------------------------------

async def _build_snapshot() -> dict[str, Any]:
    """Build a full snapshot of current system state."""
    r = await get_redis()
    factory = session_factory()

    # Agents
    raw_agents = await get_all_agents(r)
    agents: list[dict[str, Any]] = []
    for d in raw_agents:
        try:
            agents.append({
                "agent_id": d["agent_id"],
                "tier": int(d.get("tier", 1)),
                "status": d.get("status", "IDLE"),
                "current_url": d.get("current_url") or None,
                "error_count": int(d.get("error_count", 0)),
                "last_heartbeat": int(d.get("last_heartbeat", 0)) if d.get("last_heartbeat") else None,
            })
        except Exception:
            pass

    # Streams
    depths = await get_stream_depths(r)

    # Circuits
    raw_circuits = await get_all_circuits(r)
    circuits: list[dict[str, Any]] = []
    for d in raw_circuits:
        try:
            circuits.append({
                "domain": d["domain"],
                "state": d.get("state", "CLOSED"),
                "failures": int(d.get("failures", 0)),
                "last_error": d.get("last_error"),
            })
        except Exception:
            pass

    # Missions (last 50)
    mission_list: list[dict[str, Any]] = []
    try:
        async with factory() as session:
            result = await session.execute(
                select(MissionORM).order_by(MissionORM.created_at.desc()).limit(50)
            )
            rows = result.scalars().all()
            for row in rows:
                mission_list.append({
                    "id": str(row.id),
                    "name": row.name,
                    "description": row.description,
                    "config": row.config,
                    "status": row.status,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                    "job_total": row.job_total or 0,
                    "job_done": row.job_done or 0,
                    "job_failed": row.job_failed or 0,
                })
    except Exception as exc:
        logger.warning("Error fetching missions for snapshot: %s", exc)

    return {
        "type": "snapshot",
        "ts": int(time.time()),
        "data": {
            "agents": agents,
            "streams": depths,
            "circuits": circuits,
            "missions": mission_list,
        },
    }


async def _stream_push_loop() -> None:
    """
    Subscribe to live_events_channel and broadcast to WebSocket clients.
    Also push stream-depth updates every second.
    """
    redis_url = get_redis_url()
    pubsub_redis = aioredis.from_url(redis_url, encoding="utf-8", decode_responses=True)
    pubsub = pubsub_redis.pubsub()
    await pubsub.subscribe("live_events_channel")
    logger.info("WebSocket push loop started")

    last_stream_push = 0.0

    try:
        while True:
            # Check for pub/sub messages (non-blocking)
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
            if msg and msg.get("data"):
                try:
                    event = json.loads(msg["data"])
                    await manager.broadcast(event)
                except Exception as exc:
                    logger.debug("Error broadcasting pub/sub message: %s", exc)

            # Push stream depths every second
            now = time.time()
            if now - last_stream_push >= 1.0:
                last_stream_push = now
                try:
                    r = await get_redis()
                    depths = await get_stream_depths(r)
                    await manager.broadcast({
                        "type": "stream_update",
                        "ts": int(now),
                        "data": {"streams": depths},
                    })
                except Exception as exc:
                    logger.debug("Error pushing stream depths: %s", exc)

            await asyncio.sleep(0.05)
    except asyncio.CancelledError:
        pass
    finally:
        await pubsub.unsubscribe("live_events_channel")
        await pubsub_redis.aclose()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting API Gateway…")
    await init_db()
    r = await get_redis()
    await ensure_stream_groups(r)

    push_task = asyncio.create_task(_stream_push_loop())

    yield

    push_task.cancel()
    try:
        await push_task
    except asyncio.CancelledError:
        pass

    await close_redis()
    await close_db()
    logger.info("API Gateway stopped.")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="MultiAgent DataSpider — API Gateway",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(missions.router)
app.include_router(data.router)
app.include_router(monitor.router)


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws/console")
async def ws_console(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    logger.info("WebSocket client connected")
    try:
        # Send immediate snapshot
        snapshot = await _build_snapshot()
        await websocket.send_text(json.dumps(snapshot, default=str))

        # Keep connection alive; clients can send pings
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                # echo ping/pong
                if data == "ping":
                    await websocket.send_text(json.dumps({"type": "pong", "ts": int(time.time())}))
            except asyncio.TimeoutError:
                # Send a keepalive
                await websocket.send_text(json.dumps({"type": "ping", "ts": int(time.time())}))
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as exc:
        logger.warning("WebSocket error: %s", exc)
    finally:
        manager.disconnect(websocket)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
