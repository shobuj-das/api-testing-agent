"""Strict Pydantic domain models for workflows and variable extraction."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from models.dependency import VariableSourceLocation
from models.execution_models import ExecutionResult
from models.test_case import TestCase


class VariableExtractionRule(BaseModel):
    """Rule for extracting a value from a step's response into the workflow context."""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    source: VariableSourceLocation = VariableSourceLocation.BODY
    field_path: str = Field(min_length=1)
    variable_name: str = Field(min_length=1)
    default: Any | None = None
    required: bool = True


class WorkflowStep(BaseModel):
    """A single executable step within an end-to-end API workflow."""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    step_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=240)
    description: str | None = None
    test_case: TestCase
    extract_variables: list[VariableExtractionRule] = Field(default_factory=list)
    continue_on_failure: bool = False
    is_cleanup: bool = False


class Workflow(BaseModel):
    """A sequence of dependent API operations executed in order."""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=240)
    description: str = Field(min_length=1)
    steps: list[WorkflowStep] = Field(default_factory=list)
    initial_variables: dict[str, Any] = Field(default_factory=dict)


class StepExecutionResult(BaseModel):
    """Execution result for an individual workflow step including extracted data."""

    model_config = ConfigDict(extra="forbid", strict=True)

    step_id: str = Field(min_length=1)
    execution_result: ExecutionResult
    extracted_variables: dict[str, Any] = Field(default_factory=dict)
    passed: bool


class WorkflowExecutionResult(BaseModel):
    """Structured outcome of executing an entire workflow."""

    model_config = ConfigDict(extra="forbid", strict=True)

    workflow_id: str = Field(min_length=1)
    workflow_name: str = Field(min_length=1)
    passed: bool
    step_results: list[StepExecutionResult] = Field(default_factory=list)
    final_variables: dict[str, Any] = Field(default_factory=dict)
    failure_reason: str | None = None
    duration_ms: float = Field(default=0.0, ge=0.0)
