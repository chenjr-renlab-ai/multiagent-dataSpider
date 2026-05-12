"""
Store Worker: consumes from validated_data stream.
- Writes ScrapedData to PostgreSQL
- Increments mission job_done / job_failed counters
- Publishes mission_event when counters change
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import time
import uuid
from typing import Any

from sqlalchemy import update

from shared.db import MissionORM, ScrapedDataORM, session_factory
from shared.redis_client import (
    GROUP_STORES,
    STREAM_VALIDATED_DATA,
    agent_heartbeat,
    get_redis,
    move_to_dead_letters,
    publish_live_event,
    xack,
    xclaim_pending,
    xadd,
    xread_group,
)

logger = logging.getLogger(__name__)

WORKER_TIER = 5


class StoreWorker:
    def __init__(self) -> None:
        self.agent_id = f"store-{socket.gethostname()}-{os.getpid()}"
        self._error_count = 0
        self._running = False

    async def run(self) -> None:
        self._running = True
        r = await get_redis()
        logger.info("Store worker %s starting", self.agent_id)

        while self._running:
            try:
                pending = await xclaim_pending(r, STREAM_VALIDATED_DATA, GROUP_STORES, self.agent_id)
                for msg_id, data in pending:
                    await self._process_message(r, msg_id, data)

                messages = await xread_group(
                    r, STREAM_VALIDATED_DATA, GROUP_STORES, self.agent_id,
                    count=20, block_ms=2000,
                )
                for msg_id, data in messages:
                    await self._process_message(r, msg_id, data)

                if not messages and not pending:
                    await agent_heartbeat(r, self.agent_id, "IDLE", WORKER_TIER, error_count=self._error_count)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Store loop error: %s", exc)
                self._error_count += 1
                await asyncio.sleep(1)

    async def _process_message(self, r, msg_id: str, data: dict) -> None:
        mission_id_str = data.get("mission_id", "")
        target_url = data.get("target_url", "")
        extracted_str = data.get("extracted_fields", "{}")
        confidence_str = data.get("confidence", "1.0")

        await agent_heartbeat(r, self.agent_id, "PROCESSING", WORKER_TIER, current_url=target_url)

        try:
            mission_id = uuid.UUID(mission_id_str) if mission_id_str else None
        except ValueError:
            mission_id = None

        try:
            extracted_fields: dict[str, Any] = json.loads(extracted_str)
        except json.JSONDecodeError:
            extracted_fields = {}

        try:
            confidence = float(confidence_str)
        except (ValueError, TypeError):
            confidence = 1.0

        success = False
        try:
            factory = session_factory()
            async with factory() as session:
                scraped = ScrapedDataORM(
                    id=uuid.uuid4(),
                    mission_id=mission_id,
                    target_url=target_url,
                    extracted_fields=extracted_fields,
                    confidence=confidence,
                )
                session.add(scraped)

                # Increment job_done on the mission
                if mission_id is not None:
                    await session.execute(
                        update(MissionORM)
                        .where(MissionORM.id == mission_id)
                        .values(job_done=MissionORM.job_done + 1)
                    )

                await session.commit()
                success = True
                logger.info("Stored %s (confidence=%.3f)", target_url, confidence)

        except Exception as exc:
            logger.error("DB write error for %s: %s", target_url, exc)
            self._error_count += 1
            # Increment job_failed
            try:
                factory = session_factory()
                async with factory() as session:
                    if mission_id is not None:
                        await session.execute(
                            update(MissionORM)
                            .where(MissionORM.id == mission_id)
                            .values(job_failed=MissionORM.job_failed + 1)
                        )
                    await session.commit()
            except Exception as inner_exc:
                logger.error("Failed to increment job_failed: %s", inner_exc)

            await move_to_dead_letters(r, data, f"db_error:{str(exc)[:100]}")

        await xack(r, STREAM_VALIDATED_DATA, GROUP_STORES, msg_id)

        # Emit mission progress event
        if mission_id is not None:
            try:
                await publish_live_event(r, {
                    "type": "mission_event",
                    "ts": int(time.time()),
                    "data": {
                        "mission_id": str(mission_id),
                        "event": "progress",
                        "detail": {
                            "target_url": target_url,
                            "stored": success,
                            "confidence": confidence,
                        },
                    },
                })
            except Exception as exc:
                logger.debug("Failed to publish mission progress event: %s", exc)
