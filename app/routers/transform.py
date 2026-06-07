"""Transform endpoint — applies approved JSONata mapping to raw events."""
import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import MappingRecord, MappingStatus, TransformRequest, TransformResponse
from app.services.jsonata_runner import JSONataError, evaluate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/transform", tags=["transform"])


@router.post("", response_model=TransformResponse)
async def transform_event(body: TransformRequest, db: AsyncSession = Depends(get_db)):
    """Apply an approved JSONata mapping to a raw source event."""
    record = (
        await db.execute(select(MappingRecord).where(MappingRecord.id == body.source_id))
    ).scalar_one_or_none()

    if not record:
        raise HTTPException(status_code=404, detail=f"Source mapping {body.source_id!r} not found.")
    if record.status != MappingStatus.approved:
        raise HTTPException(
            status_code=422,
            detail=f"Mapping is '{record.status}'. Only approved mappings can be used for transforms.",
        )

    t0 = time.perf_counter()
    try:
        canonical = await evaluate(record.expression, body.payload)
        record.transform_count += 1
    except JSONataError as exc:
        record.error_count += 1
        logger.error("Transform failed", extra={"source_id": body.source_id, "error": str(exc)})
        raise HTTPException(status_code=500, detail=f"JSONata evaluation error: {exc}")
    finally:
        await db.commit()

    duration_ms = round((time.perf_counter() - t0) * 1000, 2)
    logger.info("Transform completed", extra={"source_id": body.source_id, "duration_ms": duration_ms})

    return TransformResponse(
        source_id=body.source_id,
        source_name=record.source_name,
        canonical=canonical,
        duration_ms=duration_ms,
    )
