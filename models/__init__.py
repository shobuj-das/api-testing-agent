"""Validated domain objects passed between agents and deterministic tools."""

from models.api_models import APIEndpoint, APIParameter, APISpecification, HTTPMethod
from models.agent_state import AgentAction, AgentDecision, AgentState
from models.api_understanding import EndpointUnderstanding
from models.dependency import (
    APIDependency,
    ConsumedVariable,
    DependencyGraph,
    DependencyType,
    ProducedVariable,
    VariableSourceLocation,
)
from models.execution_models import ExecutionResult, ExecutionStatus
from models.failure_analysis import FailureAnalysis, FailureCategory
from models.test_generation import GeneratedTestBatch
from models.test_case import Assertion, AssertionType, TestCase
from models.test_plan import TestPlan
from models.workflow import (
    StepExecutionResult,
    VariableExtractionRule,
    Workflow,
    WorkflowExecutionResult,
    WorkflowStep,
)

__all__ = [
    "APIDependency",
    "APIEndpoint",
    "AgentAction",
    "AgentDecision",
    "AgentState",
    "APIParameter",
    "APISpecification",
    "Assertion",
    "AssertionType",
    "ConsumedVariable",
    "DependencyGraph",
    "DependencyType",
    "ExecutionResult",
    "FailureAnalysis",
    "FailureCategory",
    "GeneratedTestBatch",
    "EndpointUnderstanding",
    "ExecutionStatus",
    "HTTPMethod",
    "ProducedVariable",
    "StepExecutionResult",
    "TestCase",
    "TestPlan",
    "VariableExtractionRule",
    "VariableSourceLocation",
    "Workflow",
    "WorkflowExecutionResult",
    "WorkflowStep",
]
