"""
Pydantic data models shared across all services.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class MissionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TargetType(str, Enum):
    API = "api"
    HTML = "html"
    BROWSER = "browser"


class ScheduleType(str, Enum):
    ONCE = "once"
    INTERVAL = "interval"
    CRON = "cron"


class AgentStatus(str, Enum):
    IDLE = "IDLE"
    PROCESSING = "PROCESSING"
    ERROR = "ERROR"
    STOPPED = "STOPPED"


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


# ---------------------------------------------------------------------------
# Extract configuration
# ---------------------------------------------------------------------------

class ExtractConfig(BaseModel):
    type: str  # "json_path" | "css" | "xpath" | "regex"
    rules: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Mission target
# ---------------------------------------------------------------------------

class MissionTarget(BaseModel):
    url: str
    type: TargetType = TargetType.HTML
    method: str = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    body: Optional[dict[str, Any]] = None
    extract: Optional[ExtractConfig] = None
    timeout_seconds: int = 30


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

class Schedule(BaseModel):
    type: ScheduleType = ScheduleType.ONCE
    interval_seconds: Optional[int] = None
    cron_expr: Optional[str] = None


# ---------------------------------------------------------------------------
# Mission create / response
# ---------------------------------------------------------------------------

class MissionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    targets: list[MissionTarget] = Field(..., min_length=1)
    schedule: Schedule = Field(default_factory=Schedule)


class MissionResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str]
    config: dict[str, Any]
    status: MissionStatus
    created_at: datetime
    completed_at: Optional[datetime]
    job_total: int
    job_done: int
    job_failed: int

    class Config:
        from_attributes = True


class MissionListResponse(BaseModel):
    items: list[MissionResponse]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Job Envelope (sent through crawl_jobs stream)
# ---------------------------------------------------------------------------

class JobEnvelope(BaseModel):
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    mission_id: str
    target_url: str
    target_type: str = "html"
    method: str = "GET"
    headers: str = "{}"           # JSON-serialised dict
    extract_config: str = "{}"    # JSON-serialised ExtractConfig
    retry_count: str = "0"

    def to_redis_dict(self) -> dict[str, str]:
        """Convert to flat string dict for Redis Streams XADD."""
        return {
            "job_id": self.job_id,
            "mission_id": self.mission_id,
            "target_url": self.target_url,
            "target_type": self.target_type,
            "method": self.method,
            "headers": self.headers,
            "extract_config": self.extract_config,
            "retry_count": self.retry_count,
        }

    @classmethod
    def from_redis_dict(cls, data: dict[str, Any]) -> "JobEnvelope":
        """Parse from Redis Streams message dict."""
        return cls(
            job_id=data.get("job_id", str(uuid.uuid4())),
            mission_id=data["mission_id"],
            target_url=data["target_url"],
            target_type=data.get("target_type", "html"),
            method=data.get("method", "GET"),
            headers=data.get("headers", "{}"),
            extract_config=data.get("extract_config", "{}"),
            retry_count=data.get("retry_count", "0"),
        )


# ---------------------------------------------------------------------------
# Scraped data
# ---------------------------------------------------------------------------

class ScrapedDataItem(BaseModel):
    id: Optional[uuid.UUID] = None
    mission_id: uuid.UUID
    target_url: str
    extracted_fields: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 1.0
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ScrapedDataListResponse(BaseModel):
    items: list[ScrapedDataItem]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Agent info
# ---------------------------------------------------------------------------

class AgentInfo(BaseModel):
    agent_id: str
    tier: int = 1
    status: AgentStatus = AgentStatus.IDLE
    current_url: Optional[str] = None
    error_count: int = 0
    last_heartbeat: Optional[int] = None  # unix timestamp


# ---------------------------------------------------------------------------
# Stream info
# ---------------------------------------------------------------------------

class StreamInfo(BaseModel):
    name: str
    depth: int


# ---------------------------------------------------------------------------
# Circuit breaker info
# ---------------------------------------------------------------------------

class CircuitInfo(BaseModel):
    domain: str
    state: CircuitState
    failures: int = 0
    last_error: Optional[str] = None


# ---------------------------------------------------------------------------
# WebSocket push messages
# ---------------------------------------------------------------------------

class WsMessage(BaseModel):
    type: str
    ts: int
    data: Any


class SnapshotData(BaseModel):
    agents: list[AgentInfo]
    streams: list[StreamInfo]
    circuits: list[CircuitInfo]
    missions: list[MissionResponse]
