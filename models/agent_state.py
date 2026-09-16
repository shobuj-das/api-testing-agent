"""Serializable state and decisions for the bounded testing-agent loop."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from models.api_models import APISpecification
from models.api_understanding import EndpointUnderstanding
from models.execution_models import ExecutionResult
from models.failure_analysis import FailureAnalysis
from models.test_case import TestCase
from models.test_plan import TestPlan


class AgentAction(StrEnum):
    GENERATE_TEST = "GENERATE_TEST"
    EXECUTE_TEST = "EXECUTE_TEST"
    RETRY_TEST = "RETRY_TEST"
    GENERATE_ADDITIONAL_TEST = "GENERATE_ADDITIONAL_TEST"
    ANALYZE_FAILURE = "ANALYZE_FAILURE"
    BUILD_WORKFLOW = "BUILD_WORKFLOW"
    EXECUTE_WORKFLOW = "EXECUTE_WORKFLOW"
    STOP = "STOP"


class AgentDecision(BaseModel):
    """Explainable decision trace; it intentionally contains no hidden reasoning."""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    iteration: int = Field(ge=0)
    action: AgentAction
    reasoning_summary: str = Field(min_length=1, max_length=1_500)
    evidence: list[str] = Field(default_factory=list)


class AgentState(BaseModel):
    """All state needed to inspect, serialize, and later resume an agent run."""

    model_config = ConfigDict(extra="forbid", strict=True)

    api_information: APISpecification
    endpoint_understandings: list[EndpointUnderstanding] = Field(default_factory=list)
    test_plan: TestPlan | None = None
    generated_tests: list[TestCase] = Field(default_factory=list)
    execution_results: list[ExecutionResult] = Field(default_factory=list)
    failures: list[FailureAnalysis] = Field(default_factory=list)
    workflows: list[dict[str, Any]] = Field(default_factory=list)
    workflow_results: list[dict[str, Any]] = Field(default_factory=list)
    workflows_built: bool = False
    pending_workflow_index: int = Field(default=0, ge=0)
    current_action: AgentAction = AgentAction.GENERATE_TEST
    iteration: int = Field(default=0, ge=0)
    remaining_tasks: list[str] = Field(default_factory=list)
    decisions: list[AgentDecision] = Field(default_factory=list)
    retry_counts: dict[str, int] = Field(default_factory=dict)
    pending_test_ids: list[str] = Field(default_factory=list)
    pending_failure_test_id: str | None = None
    next_endpoint_index: int = Field(default=0, ge=0)
