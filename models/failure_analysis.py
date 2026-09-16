"""Validated, evidence-based failure analysis records."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FailureCategory(StrEnum):
    APPLICATION_DEFECT = "application_defect"
    TEST_DEFECT = "test_defect"
    INVALID_TEST_DATA = "invalid_test_data"
    AUTHENTICATION_ISSUE = "authentication_issue"
    AUTHORIZATION_ISSUE = "authorization_issue"
    ENVIRONMENT_ISSUE = "environment_issue"
    DEPENDENCY_ISSUE = "dependency_issue"
    CONTRACT_VIOLATION = "contract_violation"
    TIMEOUT = "timeout"
    INTERMITTENT_FAILURE = "intermittent_failure"
    UNKNOWN = "unknown"


class FailureAnalysis(BaseModel):
    """A non-conclusive AI classification with explicit supporting evidence."""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    test_id: str = Field(min_length=1)
    classification: FailureCategory
    confidence: float = Field(ge=0, le=0.95)
    conclusion: str = Field(min_length=1, max_length=1_500)
    evidence: list[str] = Field(min_length=1)
    assumptions: list[str] = Field(default_factory=list)
    recommended_next_actions: list[str] = Field(min_length=1)
    reasoning_summary: str = Field(min_length=1, max_length=1_500)

    @model_validator(mode="after")
    def uncertainty_is_calibrated(self) -> "FailureAnalysis":
        if self.classification is FailureCategory.UNKNOWN and self.confidence > 0.5:
            raise ValueError("Unknown classifications cannot have confidence above 0.5.")
        return self
