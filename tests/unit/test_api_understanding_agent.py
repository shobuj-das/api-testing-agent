"""Tests for evidence-based API understanding output and call caching."""

import pytest

from agents.api_understanding_agent import APIUnderstandingAgent, UnderstandingError
from ai.llm_client import MockLLMClient
from models.api_models import APIEndpoint, APIParameter, HTTPMethod, ParameterLocation


ENDPOINT = APIEndpoint(
    method=HTTPMethod.GET,
    path="/booking/{booking_id}",
    summary="Get booking",
    parameters=[APIParameter(
        name="booking_id", location=ParameterLocation.PATH, required=True,
        schema={"type": "integer", "minimum": 1},
    )],
    authentication_required=True,
)

VALID_UNDERSTANDING = {
    "method": "GET",
    "path": "/booking/{booking_id}",
    "purpose": "Retrieve one booking by identifier.",
    "required_inputs": [{
        "name": "booking_id", "location": "path", "data_type": "integer",
        "required": True, "constraints": {"minimum": 1},
    }],
    "optional_inputs": [],
    "response_behaviors": [{
        "status_code": "200", "behavior": "Returns the requested booking.",
        "response_fields": [], "evidence": ["OpenAPI response metadata"],
    }],
    "authentication_required": True,
    "dependency_hints": [{
        "relationship": "A booking identifier must exist before retrieval.", "confidence": 0.8,
        "evidence": ["Path parameter booking_id"],
    }],
    "negative_scenarios": ["Use an unknown booking identifier."],
    "boundary_conditions": ["Use the documented minimum booking identifier."],
    "state_transitions": ["Read existing booking state."],
    "reasoning_summary": "The path requires an integer identifier and the endpoint requires authentication.",
    "evidence": ["OpenAPI path parameter", "OpenAPI security requirement"],
}


def test_agent_returns_validated_understanding_and_caches_it() -> None:
    client = MockLLMClient([VALID_UNDERSTANDING])
    agent = APIUnderstandingAgent(client)

    first = agent.understand_endpoint(ENDPOINT)
    second = agent.understand_endpoint(ENDPOINT)

    assert first is second
    assert first.required_inputs[0].name == "booking_id"
    assert client.metrics.call_count == 1


def test_agent_rejects_output_for_a_different_endpoint() -> None:
    invalid_identity = {**VALID_UNDERSTANDING, "path": "/users/1"}
    agent = APIUnderstandingAgent(MockLLMClient([invalid_identity]))

    with pytest.raises(UnderstandingError, match="does not match"):
        agent.understand_endpoint(ENDPOINT)


def test_agent_rejects_output_that_contradicts_openapi_authentication() -> None:
    invalid_authentication = {**VALID_UNDERSTANDING, "authentication_required": False}
    agent = APIUnderstandingAgent(MockLLMClient([invalid_authentication]))

    with pytest.raises(UnderstandingError, match="authentication requirement"):
        agent.understand_endpoint(ENDPOINT)


def test_force_refresh_bypasses_cached_understanding() -> None:
    refreshed = {**VALID_UNDERSTANDING, "purpose": "Retrieve a booking record."}
    client = MockLLMClient([VALID_UNDERSTANDING, refreshed])
    agent = APIUnderstandingAgent(client)

    initial = agent.understand_endpoint(ENDPOINT)
    updated = agent.understand_endpoint(ENDPOINT, force_refresh=True)

    assert initial.purpose != updated.purpose
    assert client.metrics.call_count == 2
