"""
Scheduler: manages recurring missions using Redis Sorted Set.

Missions with schedule.type == "interval" are stored in the sorted set
  key: scheduled_missions
  score: next_run_unix_timestamp
  member: mission_id (UUID string)

The coordinator calls tick() periodically to find due missions and
re-enqueue their targets.
"""
from __future__ import annotations

import json
import logging
import time
import uuid

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db import MissionORM, session_factory
from shared.models import JobEnvelope, MissionStatus
from shared.redis_client import STREAM_CRAWL_JOBS, xadd

logger = logging.getLogger(__name__)

SCHEDULED_KEY = "scheduled_missions"


async def register_mission(r: Redis, mission_id: str, next_run: float) -> None:
    """Add or update a mission in the scheduler sorted set."""
    await r.zadd(SCHEDULED_KEY, {mission_id: next_run})
    logger.debug("Scheduled mission %s for %.0f", mission_id, next_run)


async def unregister_mission(r: Redis, mission_id: str) -> None:
    await r.zrem(SCHEDULED_KEY, mission_id)


async def tick(r: Redis) -> None:
    """
    Find all missions whose scheduled time has passed, re-enqueue their
    targets, and reschedule them based on their interval.
    """
    now = time.time()
    # Get all missions due (score <= now)
    due: list[tuple[str, float]] = await r.zrangebyscore(
        SCHEDULED_KEY, "-inf", now, withscores=True
    )
    if not due:
        return

    factory = session_factory()
    async with factory() as session:
        for mission_id_str, _ in due:
            try:
                await _process_due_mission(r, session, mission_id_str)
            except Exception as exc:
                logger.error("Error processing scheduled mission %s: %s", mission_id_str, exc)


async def _process_due_mission(r: Redis, session: AsyncSession, mission_id_str: str) -> None:
    try:
        mission_id = uuid.UUID(mission_id_str)
    except ValueError:
        await r.zrem(SCHEDULED_KEY, mission_id_str)
        return

    row: MissionORM | None = await session.get(MissionORM, mission_id)
    if row is None or row.status in (
        MissionStatus.CANCELLED.value, MissionStatus.FAILED.value
    ):
        await r.zrem(SCHEDULED_KEY, mission_id_str)
        return

    config: dict = row.config or {}
    schedule = config.get("schedule", {})
    interval = schedule.get("interval_seconds")
    targets = config.get("targets", [])

    # Re-enqueue all targets
    for target in targets:
        extract_cfg = target.get("extract") or {}
        envelope = JobEnvelope(
            mission_id=mission_id_str,
            target_url=target.get("url", ""),
            target_type=target.get("type", "html"),
            method=target.get("method", "GET"),
            headers=json.dumps(target.get("headers", {})),
            extract_config=json.dumps(extract_cfg),
            retry_count="0",
        )
        await xadd(r, STREAM_CRAWL_JOBS, envelope.to_redis_dict())

    logger.info("Re-enqueued %d targets for mission %s", len(targets), mission_id_str)

    if interval and isinstance(interval, (int, float)) and interval > 0:
        next_run = time.time() + float(interval)
        await r.zadd(SCHEDULED_KEY, {mission_id_str: next_run})
        logger.debug("Rescheduled mission %s in %ss", mission_id_str, interval)
    else:
        # One-shot: remove from scheduler
        await r.zrem(SCHEDULED_KEY, mission_id_str)
