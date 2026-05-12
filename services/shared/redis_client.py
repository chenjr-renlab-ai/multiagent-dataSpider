"""
Redis utility functions and client factory.
Supports Redis Streams consumer groups, heartbeats, circuits, and pub/sub.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Optional
from urllib.parse import urlparse

import redis.asyncio as aioredis
from redis.asyncio import Redis
from redis.exceptions import ResponseError

logger = logging.getLogger(__name__)

# Stream names
STREAM_CRAWL_JOBS = "crawl_jobs"
STREAM_RAW_DATA = "raw_data"
STREAM_CLEAN_DATA = "clean_data"
STREAM_VALIDATED_DATA = "validated_data"
STREAM_DEAD_LETTERS = "dead_letters"
STREAM_LIVE_EVENTS = "live_events"

ALL_STREAMS = [
    STREAM_CRAWL_JOBS,
    STREAM_RAW_DATA,
    STREAM_CLEAN_DATA,
    STREAM_VALIDATED_DATA,
    STREAM_DEAD_LETTERS,
    STREAM_LIVE_EVENTS,
]

# Consumer group names per stream
GROUP_CRAWLERS = "crawlers"
GROUP_PROCESSORS = "processors"
GROUP_VALIDATORS = "validators"
GROUP_STORES = "stores"

STREAM_GROUPS: dict[str, str] = {
    STREAM_CRAWL_JOBS: GROUP_CRAWLERS,
    STREAM_RAW_DATA: GROUP_PROCESSORS,
    STREAM_CLEAN_DATA: GROUP_VALIDATORS,
    STREAM_VALIDATED_DATA: GROUP_STORES,
}

# Pending message claim timeout (milliseconds)
CLAIM_TIMEOUT_MS = 60_000

_pool: Optional[Redis] = None


def get_redis_url() -> str:
    return os.environ.get("REDIS_URL", "redis://localhost:6379")


async def get_redis() -> Redis:
    """Return the shared async Redis client (lazy init)."""
    global _pool
    if _pool is None:
        _pool = aioredis.from_url(
            get_redis_url(),
            encoding="utf-8",
            decode_responses=True,
            max_connections=50,
        )
    return _pool


async def close_redis() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None


async def ensure_stream_groups(r: Redis) -> None:
    """Create consumer groups for all streams (idempotent)."""
    for stream, group in STREAM_GROUPS.items():
        try:
            await r.xgroup_create(stream, group, id="0", mkstream=True)
            logger.info("Created consumer group %s on %s", group, stream)
        except ResponseError as exc:
            if "BUSYGROUP" in str(exc):
                pass  # already exists
            else:
                raise


async def xadd(r: Redis, stream: str, data: dict[str, str]) -> str:
    """Add a message to a stream and return the message ID."""
    msg_id = await r.xadd(stream, data)
    return msg_id


async def xread_group(
    r: Redis,
    stream: str,
    group: str,
    consumer: str,
    count: int = 10,
    block_ms: int = 2000,
) -> list[tuple[str, dict[str, str]]]:
    """
    Read new messages from a consumer group.
    Returns list of (message_id, data_dict).
    """
    results = await r.xreadgroup(
        groupname=group,
        consumername=consumer,
        streams={stream: ">"},
        count=count,
        block=block_ms,
    )
    if not results:
        return []
    messages: list[tuple[str, dict[str, str]]] = []
    for _stream_name, msgs in results:
        for msg_id, data in msgs:
            messages.append((msg_id, data))
    return messages


async def xack(r: Redis, stream: str, group: str, msg_id: str) -> None:
    """Acknowledge a message."""
    await r.xack(stream, group, msg_id)


async def xclaim_pending(
    r: Redis,
    stream: str,
    group: str,
    consumer: str,
    count: int = 10,
) -> list[tuple[str, dict[str, str]]]:
    """
    Claim timed-out pending messages (XAUTOCLAIM).
    Returns (message_id, data_dict) pairs.
    """
    try:
        result = await r.xautoclaim(
            stream,
            group,
            consumer,
            min_idle_time=CLAIM_TIMEOUT_MS,
            start_id="0-0",
            count=count,
        )
        # result is (next_start_id, [(id, data), ...], [deleted_ids])
        _, claimed, _ = result
        return [(msg_id, data) for msg_id, data in claimed]
    except Exception as exc:
        logger.warning("xautoclaim error on %s: %s", stream, exc)
        return []


async def move_to_dead_letters(r: Redis, data: dict[str, str], reason: str) -> None:
    """Send a failed job to the dead_letters stream."""
    payload = dict(data)
    payload["dead_reason"] = reason
    payload["dead_ts"] = str(int(time.time()))
    await xadd(r, STREAM_DEAD_LETTERS, payload)


# ---------------------------------------------------------------------------
# Agent heartbeat helpers
# ---------------------------------------------------------------------------

async def agent_heartbeat(
    r: Redis,
    agent_id: str,
    status: str,
    tier: int = 1,
    current_url: str = "",
    error_count: int = 0,
    ttl: int = 60,
) -> None:
    key = f"agent:{agent_id}"
    await r.hset(
        key,
        mapping={
            "status": status,
            "tier": str(tier),
            "current_url": current_url,
            "error_count": str(error_count),
            "last_heartbeat": str(int(time.time())),
        },
    )
    await r.expire(key, ttl)


async def get_all_agents(r: Redis) -> list[dict[str, str]]:
    """Scan for all agent:* keys and return their hash values."""
    agents: list[dict[str, str]] = []
    async for key in r.scan_iter("agent:*"):
        data = await r.hgetall(key)
        if data:
            data["agent_id"] = key.split(":", 1)[1]
            agents.append(data)
    return agents


# ---------------------------------------------------------------------------
# Circuit breaker helpers
# ---------------------------------------------------------------------------

async def circuit_open(r: Redis, domain: str, last_error: str, ttl: int = 300) -> None:
    key = f"circuit:{domain}"
    failures = await r.hget(key, "failures") or "0"
    new_failures = int(failures) + 1
    await r.hset(key, mapping={"state": "OPEN", "failures": str(new_failures), "last_error": last_error})
    await r.expire(key, ttl)


async def circuit_close(r: Redis, domain: str) -> None:
    key = f"circuit:{domain}"
    await r.hset(key, mapping={"state": "CLOSED", "failures": "0"})
    await r.persist(key)


async def is_circuit_open(r: Redis, domain: str) -> bool:
    key = f"circuit:{domain}"
    state = await r.hget(key, "state")
    return state == "OPEN"


async def get_all_circuits(r: Redis) -> list[dict[str, str]]:
    circuits: list[dict[str, str]] = []
    async for key in r.scan_iter("circuit:*"):
        data = await r.hgetall(key)
        if data:
            data["domain"] = key.split(":", 1)[1]
            circuits.append(data)
    return circuits


# ---------------------------------------------------------------------------
# Stream depth helper
# ---------------------------------------------------------------------------

async def get_stream_depths(r: Redis) -> list[dict[str, Any]]:
    depths: list[dict[str, Any]] = []
    for stream in ALL_STREAMS:
        try:
            info = await r.xlen(stream)
            depths.append({"name": stream, "depth": info})
        except Exception:
            depths.append({"name": stream, "depth": 0})
    return depths


# ---------------------------------------------------------------------------
# Live events pub/sub (for WebSocket broadcast)
# ---------------------------------------------------------------------------

async def publish_live_event(r: Redis, event: dict[str, Any]) -> None:
    payload = json.dumps(event, default=str)
    await r.publish("live_events_channel", payload)
    # Also push to the live_events stream for persistence
    await r.xadd(STREAM_LIVE_EVENTS, {"payload": payload}, maxlen=1000, approximate=True)
