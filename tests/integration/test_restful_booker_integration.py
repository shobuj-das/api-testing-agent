"""Integration tests for Restful Booker example with safe skip behavior."""

import os
from pathlib import Path
from typing import Any

import pytest
import requests

from clients.api_client import APIClient, APIResponse
from config.settings import Environment, Settings
from executor.api_executor import APIExecutor
from executor.workflow_executor import WorkflowExecutor
from models.api_models import HTTPMethod
from models.dependency import VariableSourceLocation
from models.test_case import (
    Assertion,
    AssertionType,
    Priority,
    TestCategory as ApiTestCategory,
    TestCase as ApiTestCase,
)
from models.workflow import VariableExtractionRule, Workflow, WorkflowStep
from openapi.dependency_detector import DependencyDetector
from openapi.parser import OpenAPIParser

SPEC_PATH = Path("examples/restful_booker/openapi.json")
RESTFUL_BOOKER_URL = os.getenv("API_BASE_URL", "https://restful-booker.herokuapp.com")


def _is_service_available(url: str) -> bool:
    """Probe the service with a short timeout to decide whether integration tests can run."""
    try:
        resp = requests.get(f"{url.rstrip('/')}/ping", timeout=3.0)
        return resp.status_code in {200, 201}
    except Exception:
        return False


SERVICE_AVAILABLE = _is_service_available(RESTFUL_BOOKER_URL)


def test_restful_booker_spec_parses_cleanly() -> None:
    """Ensure the Restful Booker spec is fully compliant with OpenAPI 3.0 parser."""
    assert SPEC_PATH.exists()
    parser = OpenAPIParser()
    spec = parser.parse_file(SPEC_PATH)

    assert spec.title == "Restful Booker API"
    assert len(spec.endpoints) >= 5

    methods_paths = {(ep.method, ep.path) for ep in spec.endpoints}
    assert (HTTPMethod.POST, "/auth") in methods_paths
    assert (HTTPMethod.POST, "/booking") in methods_paths
    assert (HTTPMethod.GET, "/booking/{id}") in methods_paths
    assert (HTTPMethod.PUT, "/booking/{id}") in methods_paths
    assert (HTTPMethod.DELETE, "/booking/{id}") in methods_paths


def test_restful_booker_dependencies_detected() -> None:
    """Verify deterministic dependency detection for Restful Booker."""
    parser = OpenAPIParser()
    spec = parser.parse_file(SPEC_PATH)
    detector = DependencyDetector()
    graph = detector.detect_dependencies(spec)

    assert len(graph.dependencies) >= 2
    # Check that booking id dependency from POST /booking to GET/PUT/DELETE /booking/{id} is found
    booking_id_deps = [
        d for d in graph.dependencies
        if d.producer_path == "/booking" and d.consumer_path == "/booking/{id}"
    ]
    assert len(booking_id_deps) >= 1
    assert any(d.variable_name == "bookingid" for d in booking_id_deps)


@pytest.mark.skipif(not SERVICE_AVAILABLE, reason="Restful Booker target is unreachable or offline.")
def test_restful_booker_live_workflow() -> None:
    """Run full live workflow: Auth -> Create -> Retrieve -> Update -> Delete."""
    settings = Settings(
        api_base_url=RESTFUL_BOOKER_URL,
        environment=Environment.STAGING,
        api_timeout=10.0,
    )
    client = APIClient(settings)
    executor = APIExecutor(client)
    workflow_executor = WorkflowExecutor(executor)

    booking_body = {
        "firstname": "Integration",
        "lastname": "Tester",
        "totalprice": 250,
        "depositpaid": True,
        "bookingdates": {"checkin": "2026-05-01", "checkout": "2026-05-10"},
        "additionalneeds": "Late Checkout",
    }
    updated_booking_body = {
        "firstname": "IntegrationUpdated",
        "lastname": "Tester",
        "totalprice": 300,
        "depositpaid": True,
        "bookingdates": {"checkin": "2026-05-01", "checkout": "2026-05-12"},
        "additionalneeds": "Airport Shuttle",
    }

    step_auth = WorkflowStep(
        step_id="rb-auth",
        name="Obtain auth token",
        test_case=ApiTestCase(
            id="rb-auth-tc",
            title="Authenticate",
            description="POST /auth to obtain session token",
            method=HTTPMethod.POST,
            endpoint="/auth",
            request_body={"username": "admin", "password": "password123"},
            expected_status=200,
            category=ApiTestCategory.WORKFLOW,
            priority=Priority.CRITICAL,
            source="integration_test",
        ),
        extract_variables=[
            VariableExtractionRule(
                source=VariableSourceLocation.BODY,
                field_path="token",
                variable_name="token",
            )
        ],
    )

    step_create = WorkflowStep(
        step_id="rb-create",
        name="Create booking",
        test_case=ApiTestCase(
            id="rb-create-tc",
            title="Create booking",
            description="POST /booking to create new booking",
            method=HTTPMethod.POST,
            endpoint="/booking",
            request_body=booking_body,
            expected_status=200,
            category=ApiTestCategory.WORKFLOW,
            priority=Priority.CRITICAL,
            source="integration_test",
        ),
        extract_variables=[
            VariableExtractionRule(
                source=VariableSourceLocation.BODY,
                field_path="bookingid",
                variable_name="booking_id",
            )
        ],
    )

    step_get = WorkflowStep(
        step_id="rb-get",
        name="Retrieve booking",
        test_case=ApiTestCase(
            id="rb-get-tc",
            title="Get booking",
            description="GET /booking/{booking_id} to verify creation",
            method=HTTPMethod.GET,
            endpoint="/booking/{{booking_id}}",
            expected_status=200,
            category=ApiTestCategory.WORKFLOW,
            priority=Priority.HIGH,
            source="integration_test",
        ),
    )

    step_update = WorkflowStep(
        step_id="rb-update",
        name="Update booking",
        test_case=ApiTestCase(
            id="rb-update-tc",
            title="Update booking",
            description="PUT /booking/{booking_id} with Cookie: token={{token}}",
            method=HTTPMethod.PUT,
            endpoint="/booking/{{booking_id}}",
            headers={"Cookie": "token={{token}}"},
            request_body=updated_booking_body,
            expected_status=200,
            category=ApiTestCategory.WORKFLOW,
            priority=Priority.HIGH,
            source="integration_test",
        ),
    )

    step_delete = WorkflowStep(
        step_id="rb-delete",
        name="Delete booking",
        test_case=ApiTestCase(
            id="rb-delete-tc",
            title="Delete booking",
            description="DELETE /booking/{booking_id} with Cookie: token={{token}}",
            method=HTTPMethod.DELETE,
            endpoint="/booking/{{booking_id}}",
            headers={"Cookie": "token={{token}}"},
            expected_status=201,
            assertions=[
                Assertion(
                    assertion_type=AssertionType.STATUS_CODE_IN,
                    expected=[200, 201, 204],
                    description="Delete response code",
                )
            ],
            category=ApiTestCategory.WORKFLOW,
            priority=Priority.HIGH,
            source="integration_test",
        ),
        is_cleanup=True,
    )

    workflow = Workflow(
        id="rb-lifecycle-flow",
        name="Restful Booker Full Lifecycle",
        description="End-to-end authentication, creation, retrieval, update, and cleanup.",
        steps=[step_auth, step_create, step_get, step_update, step_delete],
    )

    result = workflow_executor.execute(workflow)
    assert result.passed is True
    assert len(result.step_results) == 5
    assert result.final_variables.get("booking_id") is not None
