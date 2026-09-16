"""Tests for structured generation scope, duplicate detection and prioritization."""

import pytest

from agents.test_generation_agent import (
    TestGenerationAgent as ApiTestGenerationAgent,
    TestGenerationError as ApiTestGenerationError,
)
from ai.llm_client import MockLLMClient
from models.api_models import APIEndpoint, HTTPMethod
from models.api_understanding import EndpointUnderstanding


ENDPOINT = APIEndpoint(method=HTTPMethod.POST, path="/booking", authentication_required=True)
UNDERSTANDING = EndpointUnderstanding(
    method="POST", path="/booking", purpose="Create a booking.", authentication_required=True,
    reasoning_summary="The endpoint creates a resource.", evidence=["OpenAPI operation"],
)
BASE_TEST = {
    "method": "POST", "endpoint": "/booking", "headers": {}, "query_params": {},
    "path_params": {}, "request_body": {"lastname": "Smith"}, "expected_status": 400,
    "expected_response_fields": [], "assertions": [], "category": "negative",
    "priority": "high", "source": "mock",
}
VALID_BATCH = {
    "test_cases": [
        {**BASE_TEST, "id": "missing-firstname", "title": "Reject missing firstname", "description": "Omit firstname."},
        {**BASE_TEST, "id": "firstname-omitted", "title": "No firstname", "description": "A duplicate request condition."},
    ],
    "reasoning_summary": "One missing-field scenario is sufficient.",
    "evidence": ["firstname is required by the API understanding"],
}


def test_generation_removes_logical_duplicates_and_records_reason() -> None:
    result = ApiTestGenerationAgent(MockLLMClient([VALID_BATCH])).generate_for_endpoint(
        ENDPOINT, UNDERSTANDING, max_tests=5,
    )

    assert len(result.test_cases) == 1
    assert result.duplicates_removed == 1
    assert result.prioritization_reasons["missing-firstname"] == (
        "authentication dependency", "negative scenario",
    )


def test_generation_rejects_test_for_another_endpoint() -> None:
    wrong_scope = {**VALID_BATCH, "test_cases": [{
        **BASE_TEST, "id": "wrong", "title": "Wrong", "description": "Wrong endpoint.",
        "endpoint": "/users",
    }]}
    agent = ApiTestGenerationAgent(MockLLMClient([wrong_scope]))

    with pytest.raises(ApiTestGenerationError, match="not POST /booking"):
        agent.generate_for_endpoint(ENDPOINT, UNDERSTANDING)


def test_generation_enforces_maximum_test_count() -> None:
    agent = ApiTestGenerationAgent(MockLLMClient([VALID_BATCH]))

    with pytest.raises(ApiTestGenerationError, match="limit is 1"):
        agent.generate_for_endpoint(ENDPOINT, UNDERSTANDING, max_tests=1)


def test_generation_rejects_mismatched_understanding_before_llm_call() -> None:
    mismatched = UNDERSTANDING.model_copy(update={"path": "/users"})
    client = MockLLMClient([VALID_BATCH])

    with pytest.raises(ApiTestGenerationError, match="does not belong"):
        ApiTestGenerationAgent(client).generate_for_endpoint(ENDPOINT, mismatched)
    assert client.metrics.call_count == 0
