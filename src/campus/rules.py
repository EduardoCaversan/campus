"""Structured rule values; provenance stays in the enclosing versioned Fact."""

from pydantic import BaseModel, ConfigDict, Field


class AttendancePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    unit: str
    maximum_absence_fraction: float = Field(ge=0, le=1)
    minimum_attendance_fraction: float = Field(ge=0, le=1)
    expression: str
    calendar_exceptions: str = "UNKNOWN"


class GradingPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = 1
    state: str = "PARTIAL"
    formula: str | None = None
    output: str | None = None
    coefficients: dict[str, str] = Field(default_factory=dict)
    constant: str = "0"
    definitions: dict[str, str] = Field(default_factory=dict)
    passing_grade: str | None = None
    scale: str | None = None
    recovery_rules: list[str] = Field(default_factory=list)
    recovery_operations: list[dict] = Field(default_factory=list)
    rounding_rules: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    excerpts: list[str] = Field(default_factory=list)


class CurriculumRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    scope: str
    required_hours: float | None = None
    attempted_hours: float | None = None
    validated_hours: float | None = None
    approved_hours: float | None = None
    remaining_hours: float | None = None
    status: str = "CONFIRMED"
    interpretation: str
