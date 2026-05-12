"""
Data query endpoints.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db import get_session, ScrapedDataORM
from shared.models import ScrapedDataItem, ScrapedDataListResponse

router = APIRouter(prefix="/api/data", tags=["data"])


@router.get("", response_model=ScrapedDataListResponse)
async def list_data(
    mission_id: Optional[uuid.UUID] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> ScrapedDataListResponse:
    offset = (page - 1) * page_size

    base_query = select(ScrapedDataORM)
    count_query = select(func.count()).select_from(ScrapedDataORM)

    if mission_id is not None:
        base_query = base_query.where(ScrapedDataORM.mission_id == mission_id)
        count_query = count_query.where(ScrapedDataORM.mission_id == mission_id)

    total_result = await session.execute(count_query)
    total = total_result.scalar_one()

    rows_result = await session.execute(
        base_query
        .order_by(ScrapedDataORM.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    rows = rows_result.scalars().all()

    items = [
        ScrapedDataItem(
            id=row.id,
            mission_id=row.mission_id,
            target_url=row.target_url or "",
            extracted_fields=row.extracted_fields or {},
            confidence=row.confidence or 1.0,
            created_at=row.created_at,
        )
        for row in rows
    ]

    return ScrapedDataListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )
