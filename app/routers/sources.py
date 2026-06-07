"""Source mapping CRUD endpoints."""
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import (
    ApproveRequest, MappingDetail, MappingListItem, MappingRecord,
    MappingStatus, OnboardRequest, OnboardResponse, ValidationDetail,
)
from app.services import llm, validator

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/sources", tags=["sources"])


@router.post("", response_model=OnboardResponse, status_code=status.HTTP_201_CREATED)
async def onboard_source(body: OnboardRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Onboard a new source: LLM generates JSONata mapping, validates coverage."""
    # Security: cap payload size
    raw_size = len(json.dumps(body.sample_payload).encode())
    if raw_size > settings.payload_max_bytes:
        raise HTTPException(status_code=413, detail=f"Payload exceeds {settings.payload_max_bytes} byte limit.")

    logger.info("Onboarding source", extra={"source": body.source_name, "category": body.source_category})

    expression, mode = await llm.generate_mapping(body.sample_payload, body.source_name)
    result = validator.analyse_expression(expression)

    record = MappingRecord(
        source_name=body.source_name,
        source_category=body.source_category,
        expression=expression,
        coverage_pct=result.coverage_pct,
        mapped_fields=result.mapped_fields,
        null_fields=result.null_fields,
        missing_fields=result.missing_fields,
        generation_mode=mode,
        status=MappingStatus.pending,
        sample_payload=body.sample_payload,
    )
    db.add(record)
    await db.flush()

    logger.info("Mapping created", extra={"id": record.id, "coverage": result.coverage_pct, "mode": mode})
    return OnboardResponse(
        id=record.id,
        source_name=record.source_name,
        source_category=record.source_category,
        expression=record.expression,
        coverage_pct=record.coverage_pct,
        mapped_fields=record.mapped_fields,
        null_fields=record.null_fields,
        missing_fields=record.missing_fields,
        generation_mode=record.generation_mode,
        status=record.status,
        field_details=[ValidationDetail(field=f.field, status=f.status) for f in result.field_details],
        created_at=record.created_at,
    )


@router.get("", response_model=list[MappingListItem])
async def list_sources(
    status_filter: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List all registered source mappings."""
    q = select(MappingRecord).order_by(MappingRecord.created_at.desc())
    if status_filter:
        q = q.where(MappingRecord.status == status_filter)
    rows = (await db.execute(q)).scalars().all()
    return [
        MappingListItem(
            id=r.id, source_name=r.source_name, source_category=r.source_category,
            coverage_pct=r.coverage_pct, status=r.status, generation_mode=r.generation_mode,
            transform_count=r.transform_count, created_at=r.created_at, approved_at=r.approved_at,
        )
        for r in rows
    ]


@router.get("/{source_id}", response_model=MappingDetail)
async def get_source(source_id: str, db: AsyncSession = Depends(get_db)):
    record = await _get_or_404(source_id, db)
    return MappingDetail(
        id=record.id, source_name=record.source_name, source_category=record.source_category,
        coverage_pct=record.coverage_pct, status=record.status, generation_mode=record.generation_mode,
        transform_count=record.transform_count, error_count=record.error_count,
        expression=record.expression, mapped_fields=record.mapped_fields,
        null_fields=record.null_fields, missing_fields=record.missing_fields,
        created_at=record.created_at, approved_at=record.approved_at, updated_at=record.updated_at,
    )


@router.put("/{source_id}/approve", response_model=MappingDetail)
async def approve_source(source_id: str, body: ApproveRequest, db: AsyncSession = Depends(get_db)):
    """Approve (and optionally patch) a mapping. Only approved mappings can be used for transforms."""
    record = await _get_or_404(source_id, db)
    if body.expression:
        record.expression = body.expression
        result = validator.analyse_expression(body.expression)
        record.coverage_pct   = result.coverage_pct
        record.mapped_fields  = result.mapped_fields
        record.null_fields    = result.null_fields
        record.missing_fields = result.missing_fields
        logger.info("Expression patched before approval", extra={"id": source_id})

    if record.coverage_pct < 60:
        raise HTTPException(status_code=422, detail="Coverage below 60% — improve mapping before approving.")

    record.status      = MappingStatus.approved
    record.approved_at = datetime.now(timezone.utc)
    logger.info("Mapping approved", extra={"id": source_id, "coverage": record.coverage_pct})
    return MappingDetail(
        id=record.id, source_name=record.source_name, source_category=record.source_category,
        coverage_pct=record.coverage_pct, status=record.status, generation_mode=record.generation_mode,
        transform_count=record.transform_count, error_count=record.error_count,
        expression=record.expression, mapped_fields=record.mapped_fields,
        null_fields=record.null_fields, missing_fields=record.missing_fields,
        created_at=record.created_at, approved_at=record.approved_at, updated_at=record.updated_at,
    )


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_source(source_id: str, db: AsyncSession = Depends(get_db)):
    record = await _get_or_404(source_id, db)
    record.status = MappingStatus.inactive
    logger.info("Mapping deactivated", extra={"id": source_id})


async def _get_or_404(source_id: str, db: AsyncSession) -> MappingRecord:
    row = (await db.execute(select(MappingRecord).where(MappingRecord.id == source_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail=f"Source mapping {source_id!r} not found.")
    return row
