"""Unit tests for Milestone 11: Workflow models and execution."""

from typing import Any

import pytest

from clients.api_client import APIResponse
from executor.api_executor import APIExecutor
from executor.workflow_executor import WorkflowExecutor, _extract_from_dict
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


class MockWorkflowAPIClient:
    def __init__(self) -> None:
        self.recorded_requests: list[dict[str, Any]] = []

    def request(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        query_params: dict[str, Any] | None = None,
        path_params: dict[str, Any] | None = None,
        json_body: Any = None,
    ) -> APIResponse:
        self.recorded_requests.append({
            "method": method,
            "path": path,
            "headers": headers or {},
            "query_params": query_params or {},
            "path_params": path_params or {},
            "json_body": json_body,
        })

        # Simulate auth endpoint
        if method == "POST" and path == "/auth":
            return APIResponse(
                status_code=200,
                headers={"Set-Cookie": "token=tok_abc123"},
                text='{"token": "tok_abc123"}',
                json_body={"token": "tok_abc123"},
                duration_ms=5,
                url="https://example.test/auth",
            )

        # Simulate create booking
        if method == "POST" and path == "/booking":
            return APIResponse(
                status_code=200,
                headers={},
                text='{"bookingid": 42, "booking": {"firstname": "Jim"}}',
                json_body={"bookingid": 42, "booking": {"firstname": "Jim"}},
                duration_ms=10,
                url="https://example.test/booking",
            )

        # Simulate get booking
        if method == "GET" and path == "/booking/42":
            return APIResponse(
                status_code=200,
                headers={},
                text='{"firstname": "Jim", "lastname": "Brown"}',
                json_body={"firstname": "Jim", "lastname": "Brown"},
                duration_ms=8,
                url="https://example.test/booking/42",
            )

        # Simulate delete booking
        if method == "DELETE" and path == "/booking/42":
            return APIResponse(
                status_code=201,
                headers={},
                text="Created",
                json_body=None,
                duration_ms=6,
                url="https://example.test/booking/42",
            )

        return APIResponse(
            status_code=404,
            headers={},
            text="Not Found",
            json_body=None,
            duration_ms=2,
            url=f"https://example.test{path}",
        )


def test_extract_from_dict() -> None:
    data = {
        "token": "secret_token",
        "booking": {"id": 100, "customer": {"name": "Alice"}},
        "items": [{"code": "A1"}, {"code": "B2"}],
    }
    assert _extract_from_dict(data, "token") == "secret_token"
    assert _extract_from_dict(data, "booking.id") == 100
    assert _extract_from_dict(data, "booking.customer.name") == "Alice"
    assert _extract_from_dict(data, "items[0].code") == "A1"
    assert _extract_from_dict(data, "items[1].code") == "B2"
    assert _extract_from_dict(data, "missing.field") is None


def test_workflow_execution_success() -> None:
    client = MockWorkflowAPIClient()
    executor = APIExecutor(client)  # type: ignore[arg-type]
    workflow_executor = WorkflowExecutor(executor)

    # Build workflow:
    # Step 1: POST /auth -> extracts token
    # Step 2: POST /booking -> extracts bookingid
    # Step 3: GET /booking/{{booking_id}} -> verifies retrieval
    # Step 4: DELETE /booking/{{booking_id}} with Cookie: token={{token}} -> cleanup
    step1 = WorkflowStep(
        step_id="step-auth",
        name="Login",
        test_case=ApiTestCase(
            id="tc-auth",
            title="Authenticate",
            description="Login to obtain token",
            method=HTTPMethod.POST,
            endpoint="/auth",
            request_body={"username": "admin", "password": "password123"},
            expected_status=200,
            category=ApiTestCategory.WORKFLOW,
            priority=Priority.CRITICAL,
            source="test",
        ),
        extract_variables=[
            VariableExtractionRule(
                source=VariableSourceLocation.BODY,
                field_path="token",
                variable_name="token",
            )
        ],
    )

    step2 = WorkflowStep(
        step_id="step-create",
        name="Create booking",
        test_case=ApiTestCase(
            id="tc-create",
            title="Create booking",
            description="Create a booking record",
            method=HTTPMethod.POST,
            endpoint="/booking",
            request_body={"firstname": "Jim"},
            expected_status=200,
            category=ApiTestCategory.WORKFLOW,
            priority=Priority.CRITICAL,
            source="test",
        ),
        extract_variables=[
            VariableExtractionRule(
                source=VariableSourceLocation.BODY,
                field_path="bookingid",
                variable_name="booking_id",
            )
        ],
    )

    step3 = WorkflowStep(
        step_id="step-get",
        name="Get booking",
        test_case=ApiTestCase(
            id="tc-get",
            title="Get booking",
            description="Get created booking",
            method=HTTPMethod.GET,
            endpoint="/booking/{{booking_id}}",
            expected_status=200,
            category=ApiTestCategory.WORKFLOW,
            priority=Priority.HIGH,
            source="test",
        ),
    )

    step4 = WorkflowStep(
        step_id="step-delete",
        name="Delete booking",
        test_case=ApiTestCase(
            id="tc-delete",
            title="Delete booking",
            description="Delete created booking",
            method=HTTPMethod.DELETE,
            endpoint="/booking/{{booking_id}}",
            headers={"Cookie": "token={{token}}"},
            expected_status=201,
            category=ApiTestCategory.WORKFLOW,
            priority=Priority.HIGH,
            source="test",
        ),
        is_cleanup=True,
    )

    workflow = Workflow(
        id="wf-booking-lifecycle",
        name="Booking Lifecycle",
        description="Login, create, get, and delete booking",
        steps=[step1, step2, step3, step4],
    )

    result = workflow_executor.execute(workflow)

    assert result.passed is True
    assert len(result.step_results) == 4
    assert result.final_variables["token"] == "***MASKED***"
    assert result.final_variables["booking_id"] == 42
    assert result.failure_reason is None

    # Verify requests
    assert len(client.recorded_requests) == 4
    assert client.recorded_requests[2]["path"] == "/booking/42"
    assert client.recorded_requests[3]["path"] == "/booking/42"
    assert client.recorded_requests[3]["headers"]["Cookie"] == "token=tok_abc123"


def test_workflow_cleanup_runs_on_step_failure() -> None:
    client = MockWorkflowAPIClient()
    executor = APIExecutor(client)  # type: ignore[arg-type]
    workflow_executor = WorkflowExecutor(executor)

    # Step 1: Create booking -> extracts booking_id=42
    # Step 2: GET /booking/999 -> fails with 404 (expected 200)
    # Step 3: GET /booking/{{booking_id}} -> should be skipped!
    # Step 4: DELETE /booking/{{booking_id}} -> is_cleanup=True, should be executed!
    step1 = WorkflowStep(
        step_id="step-create",
        name="Create booking",
        test_case=ApiTestCase(
            id="tc-create",
            title="Create booking",
            description="Create booking",
            method=HTTPMethod.POST,
            endpoint="/booking",
            expected_status=200,
            category=ApiTestCategory.WORKFLOW,
            priority=Priority.CRITICAL,
            source="test",
        ),
        extract_variables=[
            VariableExtractionRule(
                field_path="bookingid",
                variable_name="booking_id",
            )
        ],
    )

    step2_fails = WorkflowStep(
        step_id="step-fail",
        name="Failing step",
        test_case=ApiTestCase(
            id="tc-fail",
            title="Failing test",
            description="Fails with 404",
            method=HTTPMethod.GET,
            endpoint="/booking/999",
            expected_status=200,
            category=ApiTestCategory.WORKFLOW,
            priority=Priority.HIGH,
            source="test",
        ),
    )

    step3_skipped = WorkflowStep(
        step_id="step-skipped",
        name="Skipped step",
        test_case=ApiTestCase(
            id="tc-skip",
            title="Skipped step",
            description="Should not run",
            method=HTTPMethod.GET,
            endpoint="/booking/{{booking_id}}",
            expected_status=200,
            category=ApiTestCategory.WORKFLOW,
            priority=Priority.LOW,
            source="test",
        ),
    )

    step4_cleanup = WorkflowStep(
        step_id="step-cleanup",
        name="Cleanup booking",
        test_case=ApiTestCase(
            id="tc-cleanup",
            title="Cleanup step",
            description="Clean up booking",
            method=HTTPMethod.DELETE,
            endpoint="/booking/{{booking_id}}",
            expected_status=201,
            category=ApiTestCategory.WORKFLOW,
            priority=Priority.HIGH,
            source="test",
        ),
        is_cleanup=True,
    )

    workflow = Workflow(
        id="wf-failure-test",
        name="Failure with cleanup test",
        description="Verify cleanup runs when intermediate step fails",
        steps=[step1, step2_fails, step3_skipped, step4_cleanup],
    )

    result = workflow_executor.execute(workflow)

    assert result.passed is False
    assert "Step 'Failing step'" in result.failure_reason  # type: ignore[operator]

    # step1 (passed), step2 (failed), step4 (cleanup executed)
    # step3 must have been skipped
    executed_step_ids = [s.step_id for s in result.step_results]
    assert executed_step_ids == ["step-create", "step-fail", "step-cleanup"]
    assert "step-skipped" not in executed_step_ids


def test_workflow_missing_required_variable_error() -> None:
    client = MockWorkflowAPIClient()
    executor = APIExecutor(client)  # type: ignore[arg-type]
    workflow_executor = WorkflowExecutor(executor)

    # Step expects non-existent field in body
    step = WorkflowStep(
        step_id="step-bad-extract",
        name="Bad Extraction",
        test_case=ApiTestCase(
            id="tc-bad",
            title="Bad Extract",
            description="Try to extract missing property",
            method=HTTPMethod.POST,
            endpoint="/booking",
            expected_status=200,
            category=ApiTestCategory.WORKFLOW,
            priority=Priority.HIGH,
            source="test",
        ),
        extract_variables=[
            VariableExtractionRule(
                field_path="non_existent_key",
                variable_name="extracted_val",
                required=True,
            )
        ],
    )

    workflow = Workflow(
        id="wf-bad",
        name="Bad Workflow",
        description="Tests missing variable handling",
        steps=[step],
    )

    result = workflow_executor.execute(workflow)
    assert result.passed is False
    assert "Required variable 'extracted_val' not found" in result.failure_reason  # type: ignore[operator]
