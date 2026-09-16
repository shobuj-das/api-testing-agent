"""Tests for structured, calibrated failure analysis."""

import pytest

from agents.failure_analysis_agent import FailureAnalysisAgent, FailureAnalysisError
from ai.llm_client import MockLLMClient
from models.api_models import HTTPMethod
from models.execution_models import ExecutionResult, ExecutionStatus
from models.test_case import Priority, TestCase as ApiTestCase, TestCategory as ApiTestCategory


TEST_CASE = ApiTestCase(
    id="missing-firstname", title="Reject missing firstname", description="Omit firstname.",
    method=HTTPMethod.POST, endpoint="/booking", expected_status=400,
    category=ApiTestCategory.NEGATIVE, priority=Priority.HIGH, source="mock",
)
FAILED_RESULT = ExecutionResult(
    test_id="missing-firstname", status=ExecutionStatus.FAILED, duration_ms=15,
    failure_reason="Expected status code 400; actual 200.",
)
VALID_ANALYSIS = {
    "test_id": "missing-firstname",
    "classification": "application_defect",
    "confidence": 0.75,
    "conclusion": "The endpoint may not enforce the expected required-field validation.",
    "evidence": ["The expected status was 400 and the actual status was 200."],
    "assumptions": ["The OpenAPI definition marks firstname as required."],
    "recommended_next_actions": ["Confirm the documented request schema and reproduce manually."],
    "reasoning_summary": "The observed status differs from the declared validation expectation.",
}


def test_failure_agent_returns_validated_analysis_and_caches_it() -> None:
    client = MockLLMClient([VALID_ANALYSIS])
    agent = FailureAnalysisAgent(client)

    first = agent.analyze_failure(TEST_CASE, FAILED_RESULT)
    second = agent.analyze_failure(TEST_CASE, FAILED_RESULT)

    assert first is second
    assert first.classification == "application_defect"
    assert client.metrics.call_count == 1


def test_failure_agent_rejects_successful_execution() -> None:
    passed = FAILED_RESULT.model_copy(update={"status": ExecutionStatus.PASSED})

    with pytest.raises(FailureAnalysisError, match="only valid"):
        FailureAnalysisAgent(MockLLMClient([VALID_ANALYSIS])).analyze_failure(TEST_CASE, passed)


def test_failure_agent_rejects_analysis_for_another_test() -> None:
    mismatched = {**VALID_ANALYSIS, "test_id": "different-test"}

    with pytest.raises(FailureAnalysisError, match="does not match"):
        FailureAnalysisAgent(MockLLMClient([mismatched])).analyze_failure(TEST_CASE, FAILED_RESULT)


def test_unknown_analysis_cannot_overstate_confidence() -> None:
    overconfident_unknown = {**VALID_ANALYSIS, "classification": "unknown", "confidence": 0.8}

    with pytest.raises(Exception, match="Unknown classifications"):
        FailureAnalysisAgent(MockLLMClient([overconfident_unknown], max_structured_retries=0)).analyze_failure(
            TEST_CASE, FAILED_RESULT,
        )


def test_failure_agent_masks_supplied_logs_before_sending_them_to_ai() -> None:
    client = MockLLMClient([VALID_ANALYSIS])
    FailureAnalysisAgent(client).analyze_failure(
        TEST_CASE, FAILED_RESULT, logs=["Authorization: Bearer top-secret"],
    )

    assert "top-secret" not in client.calls[0][0]
