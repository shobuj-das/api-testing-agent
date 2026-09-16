"""Structured notification payloads."""
from __future__ import annotations

from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field

class NotificationSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

class FailureSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    test_id: str
    title: str
    endpoint: str
    method: str
    expected_status: int
    actual_status: int | None = None
    classification: str | None = None
    confidence: float | None = None

class TestSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    project_name: str
    total_tests: int
    passed: int
    failed: int
    errors: int
    pass_rate: float
    duration_ms: float = 0.0
    failures: list[FailureSummary] = Field(default_factory=list)
    report_url: str | None = None
