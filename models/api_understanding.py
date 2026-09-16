"""Strict evidence-based output schema for API understanding decisions."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class InputUnderstanding(BaseModel):
    """An input and the constraints relevant to test design."""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    name: str = Field(min_length=1)
    location: str = Field(min_length=1)
    data_type: str = Field(min_length=1)
    required: bool
    constraints: dict[str, Any] = Field(default_factory=dict)


class ResponseBehavior(BaseModel):
    """A documented response expectation, distinguished from inferred behavior."""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    status_code: str = Field(min_length=1)
    behavior: str = Field(min_length=1)
    response_fields: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(min_length=1)


class DependencyHint(BaseModel):
    """A tentative dependency identified from public API metadata."""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    relationship: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(min_length=1)


class EndpointUnderstanding(BaseModel):
    """Validated understanding output; concise reasoning only, never hidden reasoning."""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    method: str = Field(min_length=1)
    path: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    required_inputs: list[InputUnderstanding] = Field(default_factory=list)
    optional_inputs: list[InputUnderstanding] = Field(default_factory=list)
    response_behaviors: list[ResponseBehavior] = Field(default_factory=list)
    authentication_required: bool
    dependency_hints: list[DependencyHint] = Field(default_factory=list)
    negative_scenarios: list[str] = Field(default_factory=list)
    boundary_conditions: list[str] = Field(default_factory=list)
    state_transitions: list[str] = Field(default_factory=list)
    reasoning_summary: str = Field(min_length=1, max_length=1_500)
    evidence: list[str] = Field(min_length=1)
