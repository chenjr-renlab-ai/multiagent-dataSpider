"""
Validator Worker: consumes from clean_data stream.
- Validates extracted fields (non-empty, schema checks)
- Computes confidence score
- Publishes validated_data to the next stream
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import time
from typing import Any

from shared.redis_client import (
    GROUP_VALIDATORS,
    STREAM_CLEAN_DATA,
    STREAM_VALIDATED_DATA,
    agent_heartbeat,
    get_redis,
    move_to_dead_letters,
    xack,
    xclaim_pending,
    xadd,
    xread_group,
)

logger = logging.getLogger(__name__)

WORKER_TIER = 4
MIN_CONFIDENCE_THRESHOLD = 0.1  # below this, send to dead letters


def _compute_confidence(extracted_fields: dict[str, Any]) -> float:
    """
    Compute a confidence score in [0.0, 1.0].

    Heuristics:
    - More non-null fields = higher confidence
    - All nulls = 0.0
    - All filled = 1.0
    - Penalise very short values
    """
    if not extracted_fields:
        return 0.0

    total = len(extracted_fields)
    filled = 0
    quality_sum = 0.0

    for value in extracted_fields.values():
        if value is None:
            continue
        if isinstance(value, str):
            if len(value.strip()) == 0:
                continue
            filled += 1
            # Quality: longer values are more likely correct (up to 100 chars)
            quality_sum += min(len(value.strip()) / 100.0, 1.0)
        elif isinstance(value, (list, dict)):
            if value:
                filled += 1
                quality_sum += 1.0
        else:
            # numbers, booleans, etc.
            filled += 1
            quality_sum += 1.0

    if filled == 0:
        return 0.0

    fill_ratio = filled / total
    avg_quality = quality_sum / filled
    return round(fill_ratio * 0.6 + avg_quality * 0.4, 4)


def _validate(extracted_fields: dict[str, Any]) -> tuple[bool, str]:
    """
    Perform basic validation.
    Returns (is_valid, reason).
    """
    if not extracted_fields:
        return False, "empty_fields"
    if all(v is None for v in extracted_fields.values()):
        return False, "all_nulls"
    return True, "ok"


class ValidatorWorker:
    def __init__(self) -> None:
        self.agent_id = f"validator-{socket.gethostname()}-{os.getpid()}"
        self._error_count = 0
        self._running = False

    async def run(self) -> None:
        self._running = True
        r = await get_redis()
        logger.info("Validator worker %s starting", self.agent_id)

        while self._running:
            try:
                pending = await xclaim_pending(r, STREAM_CLEAN_DATA, GROUP_VALIDATORS, self.agent_id)
                for msg_id, data in pending:
                    await self._process_message(r, msg_id, data)

                messages = await xread_group(
                    r, STREAM_CLEAN_DATA, GROUP_VALIDATORS, self.agent_id,
                    count=10, block_ms=2000,
                )
                for msg_id, data in messages:
                    await self._process_message(r, msg_id, data)

                if not messages and not pending:
                    await agent_heartbeat(r, self.agent_id, "IDLE", WORKER_TIER, error_count=self._error_count)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Validator loop error: %s", exc)
                self._error_count += 1
                await asyncio.sleep(1)

    async def _process_message(self, r, msg_id: str, data: dict) -> None:
        mission_id = data.get("mission_id", "")
        target_url = data.get("target_url", "")
        extracted_str = data.get("extracted_fields", "{}")

        await agent_heartbeat(r, self.agent_id, "PROCESSING", WORKER_TIER, current_url=target_url)

        try:
            extracted_fields: dict[str, Any] = json.loads(extracted_str)
        except json.JSONDecodeError:
            extracted_fields = {}

        is_valid, reason = _validate(extracted_fields)
        confidence = _compute_confidence(extracted_fields)

        if not is_valid or confidence < MIN_CONFIDENCE_THRESHOLD:
            logger.warning(
                "Validation failed for %s: reason=%s confidence=%.3f",
                target_url, reason, confidence
            )
            await move_to_dead_letters(r, data, f"validation_failed:{reason}:confidence={confidence:.3f}")
            await xack(r, STREAM_CLEAN_DATA, GROUP_VALIDATORS, msg_id)
            return

        # Forward to validated_data stream
        await xadd(r, STREAM_VALIDATED_DATA, {
            "job_id": data.get("job_id", ""),
            "mission_id": mission_id,
            "target_url": target_url,
            "extracted_fields": extracted_str,
            "confidence": str(confidence),
            "validated_at": str(int(time.time())),
        })

        await xack(r, STREAM_CLEAN_DATA, GROUP_VALIDATORS, msg_id)
        logger.info("Validated %s confidence=%.3f", target_url, confidence)
