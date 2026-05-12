"""
Crawler Worker: consumes from crawl_jobs stream, fetches URLs,
and publishes raw content to raw_data stream.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import time
import uuid
from urllib.parse import urlparse

import httpx

from crawler.strategies.api_harvester import ApiHarvester
from crawler.strategies.http_crawler import HttpCrawler
from shared.models import JobEnvelope
from shared.redis_client import (
    GROUP_CRAWLERS,
    STREAM_CRAWL_JOBS,
    STREAM_RAW_DATA,
    agent_heartbeat,
    circuit_open,
    get_redis,
    is_circuit_open,
    move_to_dead_letters,
    xack,
    xclaim_pending,
    xadd,
    xread_group,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
WORKER_TIER = int(os.environ.get("WORKER_TIER", "2"))


class CrawlerWorker:
    def __init__(self) -> None:
        self.agent_id = f"crawler-{socket.gethostname()}-{os.getpid()}"
        self._error_count = 0
        self._running = False
        self._api_harvester = ApiHarvester()
        self._http_crawler = HttpCrawler()

    async def run(self) -> None:
        self._running = True
        r = await get_redis()
        logger.info("Crawler worker %s starting", self.agent_id)

        while self._running:
            try:
                # Try to claim timed-out pending messages first
                pending = await xclaim_pending(r, STREAM_CRAWL_JOBS, GROUP_CRAWLERS, self.agent_id)
                if pending:
                    for msg_id, data in pending:
                        await self._process_message(r, msg_id, data)

                # Read new messages
                messages = await xread_group(
                    r, STREAM_CRAWL_JOBS, GROUP_CRAWLERS, self.agent_id,
                    count=5, block_ms=2000,
                )
                for msg_id, data in messages:
                    await self._process_message(r, msg_id, data)

                # Idle heartbeat
                if not messages and not pending:
                    await agent_heartbeat(
                        r, self.agent_id, "IDLE", WORKER_TIER,
                        error_count=self._error_count,
                    )

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Crawler loop error: %s", exc)
                self._error_count += 1
                await asyncio.sleep(1)

        logger.info("Crawler worker %s stopped", self.agent_id)

    async def _process_message(self, r, msg_id: str, data: dict) -> None:
        try:
            envelope = JobEnvelope.from_redis_dict(data)
        except Exception as exc:
            logger.error("Invalid job envelope: %s | data=%s", exc, data)
            await xack(r, STREAM_CRAWL_JOBS, GROUP_CRAWLERS, msg_id)
            return

        domain = urlparse(envelope.target_url).netloc

        # Check circuit breaker
        if await is_circuit_open(r, domain):
            logger.warning("Circuit OPEN for %s, skipping", domain)
            await move_to_dead_letters(r, data, f"circuit_open:{domain}")
            await xack(r, STREAM_CRAWL_JOBS, GROUP_CRAWLERS, msg_id)
            return

        await agent_heartbeat(
            r, self.agent_id, "PROCESSING", WORKER_TIER,
            current_url=envelope.target_url,
            error_count=self._error_count,
        )

        try:
            raw_content, status_code, source_type = await self._fetch(envelope)

            # Publish to raw_data stream
            await xadd(r, STREAM_RAW_DATA, {
                "job_id": envelope.job_id,
                "mission_id": envelope.mission_id,
                "target_url": envelope.target_url,
                "target_type": envelope.target_type,
                "source_type": source_type,
                "raw_content": raw_content[:1_000_000],  # cap at 1MB
                "extract_config": envelope.extract_config,
                "status_code": str(status_code),
                "crawled_at": str(int(time.time())),
            })

            await xack(r, STREAM_CRAWL_JOBS, GROUP_CRAWLERS, msg_id)
            logger.info("Crawled %s -> raw_data (%d chars)", envelope.target_url, len(raw_content))

        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            retry_count = int(envelope.retry_count)

            if status in (429, 503):
                await circuit_open(r, domain, str(status))
                logger.warning("Circuit opened for %s (status %d)", domain, status)

            if retry_count < MAX_RETRIES:
                # Requeue with incremented retry count
                data["retry_count"] = str(retry_count + 1)
                await xadd(r, STREAM_CRAWL_JOBS, data)
                logger.info("Requeued %s (retry %d)", envelope.target_url, retry_count + 1)
            else:
                await move_to_dead_letters(r, data, f"http_error:{status}")
                logger.error("Max retries exceeded for %s", envelope.target_url)

            await xack(r, STREAM_CRAWL_JOBS, GROUP_CRAWLERS, msg_id)
            self._error_count += 1

        except Exception as exc:
            retry_count = int(envelope.retry_count)
            logger.error("Crawl error for %s: %s", envelope.target_url, exc)

            if retry_count < MAX_RETRIES:
                data["retry_count"] = str(retry_count + 1)
                await xadd(r, STREAM_CRAWL_JOBS, data)
            else:
                await move_to_dead_letters(r, data, str(exc)[:200])

            await xack(r, STREAM_CRAWL_JOBS, GROUP_CRAWLERS, msg_id)
            self._error_count += 1

    async def _fetch(self, envelope: JobEnvelope) -> tuple[str, int, str]:
        """Dispatch to the correct strategy based on target_type."""
        headers: dict = json.loads(envelope.headers or "{}")

        if envelope.target_type == "api":
            content, status, _ = await self._api_harvester.fetch(
                url=envelope.target_url,
                method=envelope.method,
                headers=headers,
                retry_count=int(envelope.retry_count),
            )
            return content, status, "api"
        else:
            # html or browser (fall back to http crawler)
            content, status, _ = await self._http_crawler.fetch(
                url=envelope.target_url,
                headers=headers,
                retry_count=int(envelope.retry_count),
            )
            return content, status, "html"
