"""
Validator service entry point.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal

from shared.redis_client import close_redis, ensure_stream_groups, get_redis
from validator.worker import ValidatorWorker

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)


async def main() -> None:
    logger.info("Validator service starting…")
    r = await get_redis()
    await ensure_stream_groups(r)

    worker = ValidatorWorker()

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _shutdown(*_):
        worker._running = False
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _shutdown)
        except (NotImplementedError, ValueError):
            pass

    run_task = asyncio.create_task(worker.run())
    await stop_event.wait()
    run_task.cancel()
    try:
        await run_task
    except asyncio.CancelledError:
        pass

    await close_redis()
    logger.info("Validator service stopped.")


if __name__ == "__main__":
    asyncio.run(main())
