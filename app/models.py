import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from pydantic import BaseModel, Field, field_validator


# ── ORM ──────────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


class MappingStatus(str, Enum):
    pending  = "pending"
    approved = "approved"
    inactive = "inactive"


class MappingRecord(Base):
    __tablename__ = "mappings"

    id:             Mapped[str]   = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_name:    Mapped[str]   = mapped_column(String(120), nullable=False)
    source_category:Mapped[str]   = mapped_column(String(80),  nullable=False)
    expression:     Mapped[str]   = mapped_column(Text,         nullable=False)
    coverage_pct:   Mapped[float] = mapped_column(Float,        nullable=False)
    mapped_fields:  Mapped[int]   = mapped_column(Integer,      nullable=False)
    null_fields:    Mapped[int]   = mapped_column(Integer,      nullable=False)
    missing_fields: Mapped[int]   = mapped_column(Integer,      nullable=False)
    generation_mode:Mapped[str]   = mapped_column(String(20),   nullable=False, default="api")
    status:         Mapped[str]   = mapped_column(String(20),   nullable=False, default=MappingStatus.pending)
    sample_payload: Mapped[dict]  = mapped_column(JSON,         nullable=False)
    transform_count:Mapped[int]   = mapped_column(Integer,      nullable=False, default=0)
    error_count:    Mapped[int]   = mapped_column(Integer,      nullable=False, default=0)
    created_at:     Mapped[datetime] = mapped_column(DateTime,  default=func.now())
    updated_at:     Mapped[datetime] = mapped_column(DateTime,  default=func.now(), onupdate=func.now())
    approved_at:    Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class OnboardRequest(BaseModel):
    source_name:     str  = Field(..., min_length=1, max_length=120, description="Human-readable source system name")
    source_category: str  = Field(..., min_length=1, max_length=80,  description="Category e.g. CRM, IVR, Chat")
    sample_payload:  dict = Field(..., description="Representative JSON payload from the source system")

    @field_validator("source_name")
    @classmethod
    def sanitise_name(cls, v: str) -> str:
        return v.strip()


class ValidationDetail(BaseModel):
    field:  str
    status: str          # mapped | null | missing


class OnboardResponse(BaseModel):
    id:              str
    source_name:     str
    source_category: str
    expression:      str
    coverage_pct:    float
    mapped_fields:   int
    null_fields:     int
    missing_fields:  int
    generation_mode: str
    status:          str
    field_details:   list[ValidationDetail]
    created_at:      datetime


class MappingListItem(BaseModel):
    id:              str
    source_name:     str
    source_category: str
    coverage_pct:    float
    status:          str
    generation_mode: str
    transform_count: int
    created_at:      datetime
    approved_at:     datetime | None


class MappingDetail(MappingListItem):
    expression:      str
    mapped_fields:   int
    null_fields:     int
    missing_fields:  int
    error_count:     int
    updated_at:      datetime


class ApproveRequest(BaseModel):
    expression: str | None = Field(None, description="Optionally override the generated expression before approving")


class TransformRequest(BaseModel):
    source_id: str = Field(..., description="Mapping registry ID")
    payload:   dict = Field(..., description="Raw source event payload to transform")


class TransformResponse(BaseModel):
    source_id:   str
    source_name: str
    canonical:   dict[str, Any]
    duration_ms: float


class HealthResponse(BaseModel):
    status:  str
    version: str
    env:     str


class MetricsResponse(BaseModel):
    total_mappings:    int
    approved_mappings: int
    pending_mappings:  int
    total_transforms:  int
    total_errors:      int
