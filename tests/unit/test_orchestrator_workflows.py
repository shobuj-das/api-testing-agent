"""Unit tests for orchestrator integration with workflows."""

from typing import Any

from agents.api_understanding_agent import APIUnderstandingAgent
from agents.failure_analysis_agent import FailureAnalysisAgent
from agents.orchestrator import AgentOrchestrator
from agents.test_generation_agent import TestGenerationAgent as ApiTestGenerationAgent
from agents.workflow_builder import WorkflowBuilder
from ai.llm_client import MockLLMClient
from clients.api_client import APIResponse
from executor.api_executor import APIExecutor
from executor.workflow_executor import WorkflowExecutor
from models.agent_state import AgentAction
from models.api_models import APIEndpoint, APIParameter, APIResponseDefinition, APISpecification, HTTPMethod, ParameterLocation
from openapi.dependency_detector import DependencyDetector


class MockLifecycleAPIClient:
    def __init__(self) -> None:
        self.call_count = 0

    def request(self, method: str, path: str, **kwargs: Any) -> APIResponse:
        self.call_count += 1
        if method == "POST" and path == "/booking":
            return APIResponse(
                status_code=200,
                headers={},
                text='{"bookingid": 123}',
                json_body={"bookingid": 123},
                duration_ms=5,
                url="https://example.test/booking",
            )
        if method == "GET" and path == "/booking/123":
            return APIResponse(
                status_code=200,
                headers={},
                text='{"firstname": "Sally"}',
                json_body={"firstname": "Sally"},
                duration_ms=5,
                url="https://example.test/booking/123",
            )
        return APIResponse(
            status_code=200,
            headers={},
            text="{}",
            json_body={},
            duration_ms=5,
            url=f"https://example.test{path}",
        )


def test_orchestrator_executes_workflows_when_enabled() -> None:
    understanding = {
        "method": "POST", "path": "/booking", "purpose": "Create a booking.",
        "required_inputs": [], "optional_inputs": [], "response_behaviors": [],
        "authentication_required": False, "dependency_hints": [], "negative_scenarios": [],
        "boundary_conditions": [], "state_transitions": [],
        "reasoning_summary": "Creates booking.", "evidence": ["OpenAPI operation"],
    }
    understanding_get = {
        "method": "GET", "path": "/booking/{booking_id}", "purpose": "Get a booking.",
        "required_inputs": [{"name": "booking_id", "location": "path", "data_type": "integer", "required": True}],
        "optional_inputs": [], "response_behaviors": [],
        "authentication_required": False, "dependency_hints": [], "negative_scenarios": [],
        "boundary_conditions": [], "state_transitions": [],
        "reasoning_summary": "Gets booking.", "evidence": ["OpenAPI operation"],
    }
    batch_post = {
        "test_cases": [{
            "id": "post-booking-tc", "title": "Create booking", "description": "POST booking",
            "method": "POST", "endpoint": "/booking", "headers": {}, "query_params": {},
            "path_params": {}, "request_body": {"firstname": "Sally"}, "expected_status": 200,
            "expected_response_fields": [], "assertions": [], "category": "functional",
            "priority": "high", "source": "mock",
        }],
        "reasoning_summary": "POST test.", "evidence": ["OpenAPI"],
    }
    batch_get = {
        "test_cases": [{
            "id": "get-booking-tc", "title": "Get booking", "description": "GET booking",
            "method": "GET", "endpoint": "/booking/{booking_id}", "headers": {}, "query_params": {},
            "path_params": {"booking_id": 123}, "request_body": None, "expected_status": 200,
            "expected_response_fields": [], "assertions": [], "category": "functional",
            "priority": "medium", "source": "mock",
        }],
        "reasoning_summary": "GET test.", "evidence": ["OpenAPI"],
    }

    understanding_agent = APIUnderstandingAgent(MockLLMClient([understanding, understanding_get]))
    generation_agent = ApiTestGenerationAgent(MockLLMClient([batch_post, batch_get]))
    failure_agent = FailureAnalysisAgent(MockLLMClient([]))
    client = MockLifecycleAPIClient()
    executor = APIExecutor(client)  # type: ignore[arg-type]
    workflow_executor = WorkflowExecutor(executor)
    detector = DependencyDetector()
    builder = WorkflowBuilder()

    orchestrator = AgentOrchestrator(
        understanding_agent,
        generation_agent,
        executor,
        failure_agent,
        workflow_executor=workflow_executor,
        dependency_detector=detector,
        workflow_builder=builder,
        enable_workflows=True,
        max_iterations=20,
    )

    specification = APISpecification(
        title="Booking API",
        version="1.0.0",
        openapi_version="3.0.3",
        endpoints=[
            APIEndpoint(
                method=HTTPMethod.POST,
                path="/booking",
                responses=[
                    APIResponseDefinition(
                        status_code="200",
                        description="Created",
                        schema={
                            "type": "object",
                            "properties": {"bookingid": {"type": "integer"}},
                        },
                    )
                ],
            ),
            APIEndpoint(
                method=HTTPMethod.GET,
                path="/booking/{booking_id}",
                parameters=[
                    APIParameter(
                        name="booking_id",
                        location=ParameterLocation.PATH,
                        required=True,
                        schema={"type": "integer"},
                    )
                ],
                responses=[APIResponseDefinition(status_code="200", description="Found")],
            ),
        ],
    )

    state = orchestrator.run(specification)

    assert state.current_action is AgentAction.STOP
    assert len(state.generated_tests) == 2
    assert len(state.execution_results) == 2
    assert len(state.workflows) >= 1
    assert len(state.workflow_results) >= 1
    assert state.workflow_results[0]["passed"] is True

    # Confirm decisions include BUILD_WORKFLOW and EXECUTE_WORKFLOW
    decision_actions = [d.action for d in state.decisions]
    assert AgentAction.BUILD_WORKFLOW in decision_actions
    assert AgentAction.EXECUTE_WORKFLOW in decision_actions
