"""Validated intermediate output returned by the AI test-generation step."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from models.test_case import TestCase


class GeneratedTestBatch(BaseModel):
    """AI output before deterministic deduplication and prioritization."""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    test_cases: list[TestCase] = Field(default_factory=list)
    reasoning_summary: str = Field(min_length=1, max_length=1_500)
    evidence: list[str] = Field(min_length=1)
