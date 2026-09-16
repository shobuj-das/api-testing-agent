"""Structured planning models shared by generation and orchestration layers."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from models.test_case import TestCase


class TestPlan(BaseModel):
    """A validated and de-duplicated collection of declarative test cases."""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=160)
    objective: str = Field(min_length=1)
    test_cases: list[TestCase] = Field(default_factory=list)
    reasoning_summary: str | None = None
    source: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def test_case_ids_must_be_unique(self) -> "TestPlan":
        ids = [test_case.id for test_case in self.test_cases]
        if len(ids) != len(set(ids)):
            raise ValueError("Test plan contains duplicate test-case IDs.")
        return self
