"""
Mission CRUD endpoints.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db import get_session, MissionORM
from shared.models import (
    JobEnvelope,
    MissionCreate,
    MissionListResponse,
    MissionResponse,
    MissionStatus,
)
from shared.redis_client import (
    STREAM_CRAWL_JOBS,
    get_redis,
    publish_live_event,
    xadd,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/missions", tags=["missions"])


def _orm_to_response(row: MissionORM) -> MissionResponse:
    return MissionResponse(
        id=row.id,
        name=row.name,
        description=row.description,
        config=row.config if row.config else {},
        status=MissionStatus(row.status),
        created_at=row.created_at,
        completed_at=row.completed_at,
        job_total=row.job_total or 0,
        job_done=row.job_done or 0,
        job_failed=row.job_failed or 0,
    )


@router.post("", response_model=MissionResponse, status_code=201)
async def create_mission(
    body: MissionCreate,
    session: AsyncSession = Depends(get_session),
) -> MissionResponse:
    config = body.model_dump()
    targets = config.get("targets", [])

    mission = MissionORM(
        id=uuid.uuid4(),
        name=body.name,
        description=body.description,
        config=config,
        status=MissionStatus.PENDING.value,
        job_total=len(targets),
        job_done=0,
        job_failed=0,
    )
    session.add(mission)
    await session.commit()
    await session.refresh(mission)

    # Enqueue crawl jobs
    r = await get_redis()
    for target in body.targets:
        extract_cfg = target.extract.model_dump() if target.extract else {}
        envelope = JobEnvelope(
            mission_id=str(mission.id),
            target_url=str(target.url),
            target_type=target.type.value,
            method=target.method,
            headers=json.dumps(target.headers),
            extract_config=json.dumps(extract_cfg),
            retry_count="0",
        )
        await xadd(r, STREAM_CRAWL_JOBS, envelope.to_redis_dict())

    # Update status to running
    await session.execute(
        update(MissionORM)
        .where(MissionORM.id == mission.id)
        .values(status=MissionStatus.RUNNING.value)
    )
    await session.commit()

    await publish_live_event(r, {
        "type": "mission_event",
        "ts": int(time.time()),
        "data": {
            "mission_id": str(mission.id),
            "event": "started",
            "detail": {"job_total": len(targets)},
        },
    })

    logger.info("Mission %s created with %d targets", mission.id, len(targets))
    mission.status = MissionStatus.RUNNING.value
    return _orm_to_response(mission)


@router.get("", response_model=MissionListResponse)
async def list_missions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> MissionListResponse:
    offset = (page - 1) * page_size
    total_result = await session.execute(select(func.count()).select_from(MissionORM))
    total = total_result.scalar_one()

    rows_result = await session.execute(
        select(MissionORM)
        .order_by(MissionORM.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    rows = rows_result.scalars().all()

    return MissionListResponse(
        items=[_orm_to_response(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{mission_id}", response_model=MissionResponse)
async def get_mission(
    mission_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> MissionResponse:
    row = await session.get(MissionORM, mission_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return _orm_to_response(row)


@router.delete("/{mission_id}", status_code=204)
async def cancel_mission(
    mission_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    row = await session.get(MissionORM, mission_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    if row.status in (MissionStatus.COMPLETED.value, MissionStatus.CANCELLED.value):
        raise HTTPException(status_code=409, detail=f"Mission already {row.status}")

    await session.execute(
        update(MissionORM)
        .where(MissionORM.id == mission_id)
        .values(status=MissionStatus.CANCELLED.value)
    )
    await session.commit()

    r = await get_redis()
    await publish_live_event(r, {
        "type": "mission_event",
        "ts": int(time.time()),
        "data": {
            "mission_id": str(mission_id),
            "event": "cancelled",
            "detail": {},
        },
    })
