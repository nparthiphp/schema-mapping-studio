"""Health check and metrics endpoints."""
import logging
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends

from app.config import get_settings
from app.database import get_db
from app.models import HealthResponse, MappingRecord, MappingStatus, MetricsResponse

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(tags=["ops"])


@router.get("/health", response_model=HealthResponse)
async def health(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return HealthResponse(status="ok", version=settings.app_version, env=settings.env)


@router.get("/metrics", response_model=MetricsResponse)
async def metrics(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(MappingRecord))).scalars().all()
    return MetricsResponse(
        total_mappings=len(rows),
        approved_mappings=sum(1 for r in rows if r.status == MappingStatus.approved),
        pending_mappings=sum(1 for r in rows if r.status == MappingStatus.pending),
        total_transforms=sum(r.transform_count for r in rows),
        total_errors=sum(r.error_count for r in rows),
    )
