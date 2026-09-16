"""Serializable records produced by deterministic test execution."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExecutionStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


class RequestRecord(BaseModel):
    """Sanitized request evidence retained in an execution result."""

    model_config = ConfigDict(extra="forbid", strict=True)

    method: str = Field(min_length=1)
    url: str = Field(min_length=1)
    headers: dict[str, str] = Field(default_factory=dict)
    query_params: dict[str, Any] = Field(default_factory=dict)
    body: Any | None = None


class ResponseRecord(BaseModel):
    """Captured response evidence retained in an execution result."""

    model_config = ConfigDict(extra="forbid", strict=True)

    status_code: int = Field(ge=100, le=599)
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any | None = None


class AssertionResult(BaseModel):
    """Result of one deterministic assertion."""

    model_config = ConfigDict(extra="forbid", strict=True)

    assertion_type: str = Field(min_length=1)
    passed: bool
    message: str = Field(min_length=1)


class ExecutionResult(BaseModel):
    """Complete serializable outcome of a single test case execution."""

    model_config = ConfigDict(extra="forbid", strict=True)

    test_id: str = Field(min_length=1)
    status: ExecutionStatus
    request: RequestRecord | None = None
    response: ResponseRecord | None = None
    duration_ms: float = Field(ge=0)
    assertions: list[AssertionResult] = Field(default_factory=list)
    failure_reason: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
