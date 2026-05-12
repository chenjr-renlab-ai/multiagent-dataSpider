"""
Unit tests for MissionCoordinator logic.

These tests target the coordinator module in isolation.  All Redis
interactions are provided by the mock_redis fixture from conftest.py.

Because the coordinator module does not yet exist as a file this test
file also defines a reference implementation of the classes under test
so the tests are self-contained and can be run right away.  Once the
real services/coordinator/ module is implemented the import path
(currently _coordinator_impl below) should be replaced with the actual
module path.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any
from unittest.mock import AsyncMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# Reference implementation
# (replace with `from services.coordinator.coordinator import ...` once
#  the real module exists)
# ---------------------------------------------------------------------------


class DistributedLock:
    """
    Simple Redis SET NX + Lua-delete distributed lock.

    SET key value EX ttl NX  →  acquires lock if key absent
    Lua script                →  deletes key only when value matches
    """

    LUA_RELEASE = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    else
        return 0
    end
    """

    def __init__(self, redis, key: str, ttl: int = 30):
        self._redis = redis
        self._key = key
        self._ttl = ttl
        self._token = str(uuid.uuid4())

    async def acquire(self) -> bool:
        """Return True if lock acquired, False if already held."""
        result = await self._redis.set(
            self._key, self._token, ex=self._ttl, nx=True
        )
        return bool(result)

    async def release(self) -> bool:
        """Delete the lock key only if we own it (Lua script)."""
        result = await self._redis.eval(
            self.LUA_RELEASE, 1, self._key, self._token
        )
        return bool(result)


class MissionCoordinator:
    """
    Tier-1 coordinator: acquires leadership lock, dispatches jobs to the
    crawl_jobs stream, and reclaims stuck pending entries via XAUTOCLAIM.
    """

    LOCK_KEY = "coordinator:leader"
    CRAWL_STREAM = "crawl_jobs"
    CONSUMER_GROUP = "crawlers"
    CLAIM_MIN_IDLE_MS = 300_000  # 5 minutes

    def __init__(self, redis):
        self._redis = redis
        self._lock = DistributedLock(redis, self.LOCK_KEY)

    async def acquire_leadership(self) -> bool:
        """Acquire the coordinator leadership lock."""
        return await self._lock.acquire()

    async def release_leadership(self) -> bool:
        """Release the coordinator leadership lock."""
        return await self._lock.release()

    async def dispatch_job(self, job: dict[str, str]) -> bytes:
        """
        Write a job envelope to the crawl_jobs Redis Stream.
        Returns the stream entry id.
        """
        entry_id = await self._redis.xadd(self.CRAWL_STREAM, job)
        return entry_id

    async def reclaim_stuck_jobs(self, consumer_name: str) -> list[tuple]:
        """
        Use XAUTOCLAIM to reassign pending entries that have been idle
        longer than CLAIM_MIN_IDLE_MS to consumer_name.
        Returns the list of reclaimed messages.
        """
        _cursor, messages, _deleted = await self._redis.xautoclaim(
            self.CRAWL_STREAM,
            self.CONSUMER_GROUP,
            consumer_name,
            self.CLAIM_MIN_IDLE_MS,
            "0-0",
        )
        return messages


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_acquire_lock_success(mock_redis: AsyncMock) -> None:
    """
    The first call to acquire() should succeed when Redis SET NX returns
    a truthy value (lock was not held before).
    """
    # Arrange
    mock_redis.set = AsyncMock(return_value=True)
    coordinator = MissionCoordinator(mock_redis)

    # Act
    acquired = await coordinator.acquire_leadership()

    # Assert
    assert acquired is True
    mock_redis.set.assert_awaited_once()
    args, kwargs = mock_redis.set.call_args
    assert args[0] == MissionCoordinator.LOCK_KEY
    assert kwargs.get("nx") is True


@pytest.mark.asyncio
async def test_acquire_lock_fails_if_held(mock_redis: AsyncMock) -> None:
    """
    When Redis SET NX returns None (key already exists) acquire() must
    return False to signal the lock is held by another process.
    """
    # Arrange — Redis returns None to indicate the key already exists
    mock_redis.set = AsyncMock(return_value=None)
    coordinator = MissionCoordinator(mock_redis)

    # Act
    acquired = await coordinator.acquire_leadership()

    # Assert
    assert acquired is False


@pytest.mark.asyncio
async def test_release_lock_lua(mock_redis: AsyncMock) -> None:
    """
    release_leadership() must call redis.eval with the Lua script and
    pass the lock key as KEYS[1] and the lock token as ARGV[1].
    The lock is only deleted if the token matches (Lua enforces this).
    """
    # Arrange — simulate successful release (Lua returns 1)
    mock_redis.eval = AsyncMock(return_value=1)
    coordinator = MissionCoordinator(mock_redis)
    # Retrieve the token that was generated internally
    token = coordinator._lock._token

    # Act
    released = await coordinator.release_leadership()

    # Assert
    assert released is True
    mock_redis.eval.assert_awaited_once()
    eval_args = mock_redis.eval.call_args[0]
    # eval(script, num_keys, key, token)
    assert eval_args[1] == 1                          # one key
    assert eval_args[2] == MissionCoordinator.LOCK_KEY
    assert eval_args[3] == token


@pytest.mark.asyncio
async def test_release_lock_lua_wrong_token(mock_redis: AsyncMock) -> None:
    """
    When the Lua script returns 0 (token mismatch) release() returns False,
    meaning we do NOT delete a lock we don't own.
    """
    # Arrange
    mock_redis.eval = AsyncMock(return_value=0)
    coordinator = MissionCoordinator(mock_redis)

    # Act
    released = await coordinator.release_leadership()

    # Assert
    assert released is False


@pytest.mark.asyncio
async def test_dispatch_job_writes_to_stream(mock_redis: AsyncMock) -> None:
    """
    dispatch_job() must call redis.xadd with the correct stream name and
    the job dict, and must return the stream entry id provided by Redis.
    """
    # Arrange
    entry_id = b"1700000000000-0"
    mock_redis.xadd = AsyncMock(return_value=entry_id)
    coordinator = MissionCoordinator(mock_redis)
    job = {
        "job_id": str(uuid.uuid4()),
        "mission_id": str(uuid.uuid4()),
        "target_url": "https://example.com",
        "target_type": "api",
        "method": "GET",
        "headers": "{}",
        "extract_config": '{"type":"json_path","rules":{"title":"$.title"}}',
        "retry_count": "0",
    }

    # Act
    result = await coordinator.dispatch_job(job)

    # Assert
    assert result == entry_id
    mock_redis.xadd.assert_awaited_once_with(MissionCoordinator.CRAWL_STREAM, job)


@pytest.mark.asyncio
async def test_dispatch_job_stream_name(mock_redis: AsyncMock) -> None:
    """
    The stream name used by dispatch_job must be 'crawl_jobs' as defined
    in the architectural spec.
    """
    # Arrange
    mock_redis.xadd = AsyncMock(return_value=b"1-0")
    coordinator = MissionCoordinator(mock_redis)

    # Act
    await coordinator.dispatch_job({"job_id": "x", "mission_id": "y", "target_url": "u"})

    # Assert
    stream_name_used = mock_redis.xadd.call_args[0][0]
    assert stream_name_used == "crawl_jobs"


@pytest.mark.asyncio
async def test_xautoclaim_reclaims_stuck_jobs(mock_redis: AsyncMock) -> None:
    """
    reclaim_stuck_jobs() calls redis.xautoclaim with the correct stream,
    consumer group, idle-time threshold, and starting cursor '0-0'.
    Returned messages are passed through to the caller.
    """
    # Arrange — simulate one reclaimed message
    stuck_message = (b"1234567890000-0", {b"job_id": b"abc", b"target_url": b"https://x.com"})
    mock_redis.xautoclaim = AsyncMock(
        return_value=(b"0-0", [stuck_message], [])
    )
    coordinator = MissionCoordinator(mock_redis)

    # Act
    messages = await coordinator.reclaim_stuck_jobs("crawler-001")

    # Assert
    assert messages == [stuck_message]
    mock_redis.xautoclaim.assert_awaited_once_with(
        MissionCoordinator.CRAWL_STREAM,
        MissionCoordinator.CONSUMER_GROUP,
        "crawler-001",
        MissionCoordinator.CLAIM_MIN_IDLE_MS,
        "0-0",
    )


@pytest.mark.asyncio
async def test_xautoclaim_returns_empty_when_no_stuck(mock_redis: AsyncMock) -> None:
    """
    When no messages are pending beyond the idle threshold xautoclaim
    returns an empty list and reclaim_stuck_jobs() propagates that.
    """
    # Arrange
    mock_redis.xautoclaim = AsyncMock(return_value=(b"0-0", [], []))
    coordinator = MissionCoordinator(mock_redis)

    # Act
    messages = await coordinator.reclaim_stuck_jobs("crawler-001")

    # Assert
    assert messages == []
