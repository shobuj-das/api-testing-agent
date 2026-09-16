"""Tests for bounded orchestration and serializable state."""

from typing import Any

from agents.api_understanding_agent import APIUnderstandingAgent
from agents.failure_analysis_agent import FailureAnalysisAgent
from agents.orchestrator import AgentOrchestrator
from agents.test_generation_agent import TestGenerationAgent as ApiTestGenerationAgent
from ai.llm_client import MockLLMClient
from clients.api_client import APIResponse
from executor.api_executor import APIExecutor
from models.api_models import APIEndpoint, APISpecification, HTTPMethod
from models.agent_state import AgentAction


UNDERSTANDING = {
    "method": "GET", "path": "/booking/1", "purpose": "Retrieve one booking.",
    "required_inputs": [], "optional_inputs": [], "response_behaviors": [],
    "authentication_required": False, "dependency_hints": [], "negative_scenarios": [],
    "boundary_conditions": [], "state_transitions": [],
    "reasoning_summary": "The endpoint retrieves a booking.", "evidence": ["OpenAPI operation"],
}
BATCH = {
    "test_cases": [{
        "id": "get-booking", "title": "Get booking", "description": "Retrieve booking one.",
        "method": "GET", "endpoint": "/booking/1", "headers": {}, "query_params": {},
        "path_params": {}, "request_body": None, "expected_status": 200,
        "expected_response_fields": [], "assertions": [], "category": "functional",
        "priority": "high", "source": "mock",
    }],
    "reasoning_summary": "A basic retrieval test covers the documented endpoint.",
    "evidence": ["OpenAPI GET operation"],
}
FAILURE = {
    "test_id": "get-booking", "classification": "application_defect", "confidence": 0.7,
    "conclusion": "The observed response may violate the documented expectation.",
    "evidence": ["Expected 200 but observed 500."], "assumptions": [],
    "recommended_next_actions": ["Reproduce the request and inspect service logs."],
    "reasoning_summary": "The deterministic status assertion failed.",
}


class FakeAPIClient:
    def request(self, *_: Any, **__: Any) -> APIResponse:
        return APIResponse(
            status_code=500, headers={}, text="error", json_body=None,
            duration_ms=3, url="https://example.test/booking/1",
        )


def test_orchestrator_runs_bounded_loop_and_serializes_state() -> None:
    understanding_agent = APIUnderstandingAgent(MockLLMClient([UNDERSTANDING]))
    generation_agent = ApiTestGenerationAgent(MockLLMClient([BATCH]))
    failure_agent = FailureAnalysisAgent(MockLLMClient([FAILURE]))
    orchestrator = AgentOrchestrator(
        understanding_agent, generation_agent, APIExecutor(FakeAPIClient()), failure_agent,  # type: ignore[arg-type]
        max_iterations=10, max_retries=0, max_generated_tests=5,
    )
    specification = APISpecification(
        title="Booking API", version="1", openapi_version="3.0.3",
        endpoints=[APIEndpoint(method=HTTPMethod.GET, path="/booking/1")],
    )

    state = orchestrator.run(specification)

    assert state.current_action is AgentAction.STOP
    assert len(state.generated_tests) == 1
    assert len(state.execution_results) == 1
    assert len(state.failures) == 1
    assert state.test_plan is not None
    assert "generated_tests" in state.model_dump_json()


def test_orchestrator_stops_when_iteration_limit_is_reached() -> None:
    understanding_agent = APIUnderstandingAgent(MockLLMClient([UNDERSTANDING]))
    generation_agent = ApiTestGenerationAgent(MockLLMClient([BATCH]))
    failure_agent = FailureAnalysisAgent(MockLLMClient([]))
    orchestrator = AgentOrchestrator(
        understanding_agent, generation_agent, APIExecutor(FakeAPIClient()), failure_agent,  # type: ignore[arg-type]
        max_iterations=1, max_retries=0, max_generated_tests=5,
    )
    specification = APISpecification(
        title="Booking API", version="1", openapi_version="3.0.3",
        endpoints=[APIEndpoint(method=HTTPMethod.GET, path="/booking/1")],
    )

    state = orchestrator.run(specification)

    assert state.current_action is AgentAction.STOP
    assert state.iteration == 1
    assert "Maximum agent iterations reached" in state.decisions[-1].reasoning_summary
