"""
Coordinator: distributed leader election + scheduling + auto-scaling signals.

Only the elected leader performs scheduling work; other instances stay warm.
Leader election via Redis SET NX EX (TTL=30s, renewed every 10s).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import time
import uuid
from datetime import datetime, timezone

from redis.asyncio import Redis
from sqlalchemy import select, update

from coordinator.scheduler import tick
from shared.db import MissionORM, session_factory
from shared.models import MissionStatus
from shared.redis_client import (
    STREAM_CRAWL_JOBS,
    get_all_agents,
    get_redis,
    get_stream_depths,
    publish_live_event,
)

logger = logging.getLogger(__name__)

LEADER_KEY = "coordinator:leader"
LEADER_TTL = 30          # seconds
ELECTION_INTERVAL = 10   # seconds
SCHEDULE_INTERVAL = 5    # seconds

# Lua script: release lock only if we own it
_RELEASE_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


class Coordinator:
    def __init__(self) -> None:
        self.instance_id = f"coordinator-{socket.gethostname()}-{os.getpid()}"
        self._is_leader = False
        self._running = False

    # ------------------------------------------------------------------
    # Leader election
    # ------------------------------------------------------------------

    async def _try_acquire_leader(self, r: Redis) -> bool:
        result = await r.set(LEADER_KEY, self.instance_id, nx=True, ex=LEADER_TTL)
        if result:
            self._is_leader = True
            logger.info("Acquired coordinator leadership: %s", self.instance_id)
        else:
            current = await r.get(LEADER_KEY)
            if current == self.instance_id:
                # Renew TTL
                await r.expire(LEADER_KEY, LEADER_TTL)
                self._is_leader = True
            else:
                self._is_leader = False
        return self._is_leader

    async def _release_leader(self, r: Redis) -> None:
        script = r.register_script(_RELEASE_LUA)
        await script(keys=[LEADER_KEY], args=[self.instance_id])
        self._is_leader = False
        logger.info("Released coordinator leadership")

    # ------------------------------------------------------------------
    # Main loops
    # ------------------------------------------------------------------

    async def run(self) -> None:
        self._running = True
        logger.info("Coordinator starting: %s", self.instance_id)
        r = await get_redis()

        tasks = [
            asyncio.create_task(self._election_loop(r)),
            asyncio.create_task(self._schedule_loop(r)),
            asyncio.create_task(self._heartbeat_monitor_loop(r)),
            asyncio.create_task(self._mission_completion_loop(r)),
        ]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass
        finally:
            for t in tasks:
                t.cancel()
            await self._release_leader(r)

    async def _election_loop(self, r: Redis) -> None:
        while self._running:
            try:
                await self._try_acquire_leader(r)
            except Exception as exc:
                logger.error("Election loop error: %s", exc)
            await asyncio.sleep(ELECTION_INTERVAL)

    async def _schedule_loop(self, r: Redis) -> None:
        """Run the scheduler if we are the leader."""
        while self._running:
            if self._is_leader:
                try:
                    await tick(r)
                except Exception as exc:
                    logger.error("Scheduler tick error: %s", exc)
            await asyncio.sleep(SCHEDULE_INTERVAL)

    async def _heartbeat_monitor_loop(self, r: Redis) -> None:
        """
        Publish agent_update events from Redis hash data.
        Runs every 5 seconds, leader only.
        """
        while self._running:
            if self._is_leader:
                try:
                    agents = await get_all_agents(r)
                    for d in agents:
                        await publish_live_event(r, {
                            "type": "agent_update",
                            "ts": int(time.time()),
                            "data": {
                                "agent_id": d.get("agent_id", ""),
                                "tier": int(d.get("tier", 1)),
                                "status": d.get("status", "IDLE"),
                                "current_url": d.get("current_url") or "",
                                "error_count": int(d.get("error_count", 0)),
                                "last_heartbeat": int(d.get("last_heartbeat", 0))
                                    if d.get("last_heartbeat") else None,
                            },
                        })
                except Exception as exc:
                    logger.error("Heartbeat monitor error: %s", exc)
            await asyncio.sleep(5)

    async def _mission_completion_loop(self, r: Redis) -> None:
        """
        Check if any RUNNING missions have all jobs done/failed.
        Marks them COMPLETED or FAILED.
        """
        while self._running:
            if self._is_leader:
                try:
                    await self._check_mission_completion(r)
                except Exception as exc:
                    logger.error("Mission completion check error: %s", exc)
            await asyncio.sleep(10)

    async def _check_mission_completion(self, r: Redis) -> None:
        factory = session_factory()
        async with factory() as session:
            result = await session.execute(
                select(MissionORM).where(MissionORM.status == MissionStatus.RUNNING.value)
            )
            running_missions = result.scalars().all()

            for mission in running_missions:
                total = mission.job_total or 0
                done = mission.job_done or 0
                failed = mission.job_failed or 0

                if total == 0:
                    continue

                if done + failed >= total:
                    new_status = (
                        MissionStatus.FAILED.value
                        if failed > 0 and done == 0
                        else MissionStatus.COMPLETED.value
                    )
                    await session.execute(
                        update(MissionORM)
                        .where(MissionORM.id == mission.id)
                        .values(
                            status=new_status,
                            completed_at=datetime.now(timezone.utc),
                        )
                    )
                    await session.commit()
                    await publish_live_event(r, {
                        "type": "mission_event",
                        "ts": int(time.time()),
                        "data": {
                            "mission_id": str(mission.id),
                            "event": "completed" if new_status == MissionStatus.COMPLETED.value else "failed",
                            "detail": {"job_done": done, "job_failed": failed},
                        },
                    })
                    logger.info("Mission %s -> %s (done=%d, failed=%d)", mission.id, new_status, done, failed)
