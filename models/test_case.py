"""Strict test-case schema used as the only accepted AI test output format."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from models.api_models import HTTPMethod


class TestCategory(StrEnum):
    FUNCTIONAL = "functional"
    NEGATIVE = "negative"
    BOUNDARY = "boundary"
    VALIDATION = "validation"
    WORKFLOW = "workflow"
    CONTRACT = "contract"


class Priority(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AssertionType(StrEnum):
    STATUS_CODE_EQUALS = "status_code_equals"
    STATUS_CODE_IN = "status_code_in"
    RESPONSE_CONTAINS_FIELD = "response_contains_field"
    RESPONSE_FIELD_EXISTS = "response_field_exists"
    RESPONSE_FIELD_EQUALS = "response_field_equals"
    RESPONSE_FIELD_TYPE = "response_field_type"
    JSON_SCHEMA = "json_schema"
    RESPONSE_HEADER_EXISTS = "response_header_exists"
    RESPONSE_HEADER_EQUALS = "response_header_equals"
    RESPONSE_TIME_MAX_MS = "response_time_max_ms"


class Assertion(BaseModel):
    """One deterministic assertion; implementation is added in Milestone 7."""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    assertion_type: AssertionType
    target: str | None = None
    expected: Any | None = None
    description: str | None = None

    @model_validator(mode="after")
    def validate_required_fields(self) -> "Assertion":
        target_required = {
            AssertionType.RESPONSE_CONTAINS_FIELD,
            AssertionType.RESPONSE_FIELD_EXISTS,
            AssertionType.RESPONSE_FIELD_EQUALS,
            AssertionType.RESPONSE_FIELD_TYPE,
            AssertionType.RESPONSE_HEADER_EXISTS,
            AssertionType.RESPONSE_HEADER_EQUALS,
        }
        expected_required = {
            AssertionType.STATUS_CODE_EQUALS,
            AssertionType.STATUS_CODE_IN,
            AssertionType.RESPONSE_FIELD_EQUALS,
            AssertionType.RESPONSE_FIELD_TYPE,
            AssertionType.JSON_SCHEMA,
            AssertionType.RESPONSE_HEADER_EQUALS,
            AssertionType.RESPONSE_TIME_MAX_MS,
        }
        if self.assertion_type in target_required and not self.target:
            raise ValueError(f"{self.assertion_type} requires a target.")
        if self.assertion_type in expected_required and self.expected is None:
            raise ValueError(f"{self.assertion_type} requires an expected value.")
        return self


class TestCase(BaseModel):
    """Validated, declarative definition consumed by the deterministic executor."""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(min_length=1)
    method: HTTPMethod
    endpoint: str = Field(min_length=1)
    headers: dict[str, str] = Field(default_factory=dict)
    query_params: dict[str, Any] = Field(default_factory=dict)
    path_params: dict[str, Any] = Field(default_factory=dict)
    request_body: Any | None = None
    expected_status: int = Field(ge=100, le=599)
    expected_response_fields: list[str] = Field(default_factory=list)
    assertions: list[Assertion] = Field(default_factory=list)
    category: TestCategory
    priority: Priority
    source: str = Field(min_length=1, max_length=100)

    @field_validator("endpoint")
    @classmethod
    def endpoint_must_be_relative(cls, endpoint: str) -> str:
        if not endpoint.startswith("/") or "://" in endpoint:
            raise ValueError("Test endpoint must be a relative path beginning with '/'.")
        return endpoint

