from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr

T = TypeVar("T")


# ── Auth ──────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    display_name: str | None = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str | None
    role: str
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── Recordings ────────────────────────────────────────────────────────────────

class RawIQParams(BaseModel):
    dtype: str = "int16"
    layout: str = "interleaved"
    endian: str = "little"
    signed_offset: bool = True
    sample_rate_hz: float | None = None
    center_frequency_hz: float | None = None


class WavParams(BaseModel):
    stereo_mode: str = "left_is_i_right_is_q"


class RecordingUploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_filename: str
    file_hash: str
    file_size: int
    file_format: str
    status: str
    created_at: datetime


class RecordingMetadataResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    recording_id: uuid.UUID
    sample_rate: float | None
    center_frequency: float | None
    data_type: str | None
    iq_layout: str | None
    endian: str | None
    channel_count: int
    sample_width: str | None
    is_complex: bool
    metadata_source: str | None
    metadata_confidence: float | None
    raw_metadata_json: dict | None
    created_at: datetime


class RecordingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_filename: str
    file_hash: str
    file_size: int
    file_format: str
    uploaded_by: uuid.UUID
    status: str
    duration_seconds: float | None
    total_samples: int | None
    created_at: datetime
    updated_at: datetime
    metadata: RecordingMetadataResponse | None = None


class RecordingMetadataUpdate(BaseModel):
    sample_rate: float | None = None
    center_frequency: float | None = None
    data_type: str | None = None
    iq_layout: str | None = None
    endian: str | None = None
    channel_count: int | None = None
    sample_width: str | None = None
    is_complex: bool | None = None


class PreviewResponse(BaseModel):
    samples_real: list[float]
    samples_imag: list[float]
    sample_rate: float | None
    total_samples: int
    preview_count: int
    stats: dict[str, Any]


# ── Projects ──────────────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    recording_id: uuid.UUID
    selected_start_sample: int | None = None
    selected_end_sample: int | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    selected_start_sample: int | None = None
    selected_end_sample: int | None = None
    status: str | None = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    recording_id: uuid.UUID
    created_by: uuid.UUID
    status: str
    selected_start_sample: int | None
    selected_end_sample: int | None
    created_at: datetime
    updated_at: datetime


# ── Parameters ────────────────────────────────────────────────────────────────

class ParameterEstimateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    parameter_name: str
    value_json: dict
    value_type: str
    confidence: float | None
    evidence_json: dict | None
    source: str
    created_at: datetime


# ── Jobs ──────────────────────────────────────────────────────────────────────

class JobResponse(BaseModel):
    id: str
    status: str
    progress_percent: float
    current_stage: str | None
    error_message: str | None


# ── Burst Detection ───────────────────────────────────────────────────────────

class BurstResponse(BaseModel):
    start_sample: int
    end_sample: int
    start_time_s: float
    end_time_s: float
    peak_power_db: float
    mean_power_db: float
    confidence: float


class BurstDetectionResponse(BaseModel):
    bursts: list[BurstResponse]
    stats: dict[str, Any]


class SegmentInfo(BaseModel):
    start_sample: int
    end_sample: int
    duration_seconds: float | None


# ── Common ────────────────────────────────────────────────────────────────────

class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
