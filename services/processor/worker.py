"""
Processor Worker: consumes from raw_data stream.
- Extracts fields according to extract_config (json_path / css / xpath / regex)
- Deduplicates using a Redis Set (BloomFilter-lite)
- Publishes clean_data to the next stream
- Writes RawEvent to PostgreSQL
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import socket
import time
import uuid
from typing import Any

from shared.db import RawEventORM, session_factory
from shared.redis_client import (
    GROUP_PROCESSORS,
    STREAM_CLEAN_DATA,
    STREAM_RAW_DATA,
    agent_heartbeat,
    get_redis,
    move_to_dead_letters,
    xack,
    xclaim_pending,
    xadd,
    xread_group,
)

logger = logging.getLogger(__name__)

DEDUP_KEY_PREFIX = "dedup:mission:"
DEDUP_TTL = 86400 * 7  # 7 days
WORKER_TIER = 3


def _extract_json_path(content: str, rules: dict[str, str]) -> dict[str, Any]:
    """
    Simple JSONPath extraction (dollar-dot notation).
    Supports: $.key, $.key.sub, $.array[*], $.array[0]
    """
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return {}

    result: dict[str, Any] = {}
    for field, path in rules.items():
        try:
            result[field] = _resolve_json_path(data, path)
        except Exception:
            result[field] = None
    return result


def _resolve_json_path(data: Any, path: str) -> Any:
    """Minimal JSONPath resolver."""
    if not path.startswith("$"):
        return None
    parts = path[2:].split(".")  # strip "$."
    current: Any = data
    for part in parts:
        if part == "":
            continue
        # Array wildcard or index
        if "[" in part:
            key, rest = part.split("[", 1)
            rest = rest.rstrip("]")
            if key:
                current = current[key] if isinstance(current, dict) else None
            if current is None:
                return None
            if rest == "*":
                return current if isinstance(current, list) else [current]
            else:
                idx = int(rest)
                current = current[idx] if isinstance(current, list) else None
        else:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
    return current


def _extract_css(content: str, rules: dict[str, str]) -> dict[str, Any]:
    """
    CSS selector extraction using basic regex patterns.
    For production, use a proper HTML parser like BeautifulSoup.
    """
    result: dict[str, Any] = {}
    for field, selector in rules.items():
        try:
            # Try to extract text from matching tag
            # Simple heuristic: convert "tag.class" to regex
            if "." in selector:
                tag, cls = selector.split(".", 1)
                pattern = rf'<{tag}[^>]*class="[^"]*{re.escape(cls)}[^"]*"[^>]*>(.*?)</{tag}>'
            else:
                tag = selector
                pattern = rf'<{tag}[^>]*>(.*?)</{tag}>'
            match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
            if match:
                # Strip inner HTML tags
                inner = re.sub(r"<[^>]+>", "", match.group(1)).strip()
                result[field] = inner
            else:
                result[field] = None
        except Exception:
            result[field] = None
    return result


def _extract_regex(content: str, rules: dict[str, str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field, pattern in rules.items():
        try:
            match = re.search(pattern, content, re.DOTALL)
            result[field] = match.group(1) if match and match.lastindex else (match.group(0) if match else None)
        except Exception:
            result[field] = None
    return result


def _extract_fields(raw_content: str, extract_config: dict) -> dict[str, Any]:
    extract_type = extract_config.get("type", "")
    rules: dict[str, str] = extract_config.get("rules", {})

    if not rules:
        # No rules: return raw content truncated
        return {"raw": raw_content[:5000]}

    if extract_type == "json_path":
        return _extract_json_path(raw_content, rules)
    elif extract_type in ("css", "html"):
        return _extract_css(raw_content, rules)
    elif extract_type == "regex":
        return _extract_regex(raw_content, rules)
    else:
        # Best-effort: try JSON first, then CSS
        try:
            return _extract_json_path(raw_content, rules)
        except Exception:
            return _extract_css(raw_content, rules)


def _content_hash(mission_id: str, url: str, content: str) -> str:
    h = hashlib.sha256(f"{mission_id}:{url}:{content[:2000]}".encode()).hexdigest()
    return h


class ProcessorWorker:
    def __init__(self) -> None:
        self.agent_id = f"processor-{socket.gethostname()}-{os.getpid()}"
        self._error_count = 0
        self._running = False

    async def run(self) -> None:
        self._running = True
        r = await get_redis()
        logger.info("Processor worker %s starting", self.agent_id)

        while self._running:
            try:
                pending = await xclaim_pending(r, STREAM_RAW_DATA, GROUP_PROCESSORS, self.agent_id)
                for msg_id, data in pending:
                    await self._process_message(r, msg_id, data)

                messages = await xread_group(
                    r, STREAM_RAW_DATA, GROUP_PROCESSORS, self.agent_id,
                    count=10, block_ms=2000,
                )
                for msg_id, data in messages:
                    await self._process_message(r, msg_id, data)

                if not messages and not pending:
                    await agent_heartbeat(r, self.agent_id, "IDLE", WORKER_TIER, error_count=self._error_count)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Processor loop error: %s", exc)
                self._error_count += 1
                await asyncio.sleep(1)

    async def _process_message(self, r, msg_id: str, data: dict) -> None:
        mission_id = data.get("mission_id", "")
        target_url = data.get("target_url", "")
        raw_content = data.get("raw_content", "")
        extract_config_str = data.get("extract_config", "{}")
        job_id = data.get("job_id", str(uuid.uuid4()))
        source_type = data.get("source_type", "html")

        await agent_heartbeat(r, self.agent_id, "PROCESSING", WORKER_TIER, current_url=target_url)

        try:
            extract_config = json.loads(extract_config_str)
        except json.JSONDecodeError:
            extract_config = {}

        # Deduplication
        content_hash = _content_hash(mission_id, target_url, raw_content)
        dedup_key = f"{DEDUP_KEY_PREFIX}{mission_id}"
        already_seen = await r.sismember(dedup_key, content_hash)
        if already_seen:
            logger.debug("Duplicate content for %s, skipping", target_url)
            await xack(r, STREAM_RAW_DATA, GROUP_PROCESSORS, msg_id)
            return

        # Extract fields
        try:
            extracted = _extract_fields(raw_content, extract_config)
        except Exception as exc:
            logger.warning("Extraction error for %s: %s", target_url, exc)
            extracted = {"raw_snippet": raw_content[:1000]}

        # Persist raw event to DB
        try:
            factory = session_factory()
            async with factory() as session:
                raw_event = RawEventORM(
                    id=uuid.uuid4(),
                    mission_id=uuid.UUID(mission_id) if mission_id else None,
                    target_url=target_url,
                    source_type=source_type,
                    raw_content=raw_content[:100_000],
                )
                session.add(raw_event)
                await session.commit()
        except Exception as exc:
            logger.warning("DB write error for raw_event: %s", exc)

        # Mark content as seen
        await r.sadd(dedup_key, content_hash)
        await r.expire(dedup_key, DEDUP_TTL)

        # Forward to clean_data stream
        await xadd(r, STREAM_CLEAN_DATA, {
            "job_id": job_id,
            "mission_id": mission_id,
            "target_url": target_url,
            "extracted_fields": json.dumps(extracted, default=str),
            "source_type": source_type,
            "processed_at": str(int(time.time())),
        })

        await xack(r, STREAM_RAW_DATA, GROUP_PROCESSORS, msg_id)
        logger.info("Processed %s -> %d fields", target_url, len(extracted))
