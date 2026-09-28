from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class State(StrEnum):
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    CONFLICT = "CONFLICT"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"


class Fact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: str = Field(min_length=1, max_length=300)
    kind: str = Field(pattern=r"^[a-z_]+$")
    field: str = Field(pattern=r"^[a-z_]+$")
    value: Any
    source: str = Field(min_length=1, max_length=100)
    external_ref: str = Field(min_length=1, max_length=2000)
    observed_at: str = Field(default_factory=now)
    confidence: float = Field(default=1.0, ge=0, le=1)
    excerpt: str = Field(default="", max_length=100000)

    @field_validator("observed_at")
    @classmethod
    def timestamp(cls, value: str) -> str:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError("observed_at requires a timezone")
        if parsed > datetime.now(UTC):
            raise ValueError("observed_at cannot be in the future")
        return parsed.astimezone(UTC).isoformat(timespec="seconds")


class ProviderResult(BaseModel):
    provider: str
    state: State
    authenticated: bool | None = None
    message: str = ""
    facts: list[Fact] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checked_at: str = Field(default_factory=now)


class CampusError(Exception):
    """Safe, intentionally authored error; never wrap raw provider exceptions."""

    def __init__(self, message: str, state: State = State.FAILED):
        super().__init__(message)
        self.state = state
