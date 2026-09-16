"""Tests for deterministic test-case execution and variable resolution."""

from typing import Any

from clients.api_client import APIResponse
from executor.api_executor import APIExecutor
from models.execution_models import ExecutionStatus
from models.test_case import Assertion, AssertionType, TestCase as ApiTestCase


class FakeAPIClient:
    def __init__(self, response: APIResponse) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, path: str, **kwargs: Any) -> APIResponse:
        self.calls.append({"method": method, "path": path, **kwargs})
        return self.response


def build_test_case(**overrides: object) -> ApiTestCase:
    data: dict[str, object] = {
        "id": "get-booking", "title": "Get booking", "description": "Retrieve a booking.",
        "method": "GET", "endpoint": "/booking/{booking_id}", "expected_status": 200,
        "category": "functional", "priority": "high", "source": "unit-test",
    }
    data.update(overrides)
    return ApiTestCase.model_validate_json(
        __import__("json").dumps(
            data, default=lambda item: item.model_dump(mode="json"),
        )
    )


def test_executor_resolves_variables_masks_evidence_and_passes() -> None:
    client = FakeAPIClient(APIResponse(
        status_code=200, headers={"Content-Type": "application/json"}, text='{"id": 42}',
        json_body={"id": 42}, duration_ms=4, url="https://example.test/booking/42",
    ))
    test_case = build_test_case(
        headers={"Authorization": "Bearer {{token}}"}, path_params={"booking_id": "{{booking_id}}"},
        assertions=[Assertion(assertion_type=AssertionType.RESPONSE_FIELD_EQUALS, target="id", expected=42)],
    )

    result = APIExecutor(client).execute(test_case, variables={"token": "secret", "booking_id": 42})  # type: ignore[arg-type]

    assert result.status is ExecutionStatus.PASSED
    assert client.calls[0]["path_params"] == {"booking_id": 42}
    assert result.request is not None
    assert result.request.headers["Authorization"] == "***MASKED***"


def test_executor_returns_failed_result_for_assertion_failure() -> None:
    client = FakeAPIClient(APIResponse(
        status_code=500, headers={}, text="", json_body=None, duration_ms=1, url="https://example.test/booking",
    ))

    result = APIExecutor(client).execute(build_test_case())  # type: ignore[arg-type]

    assert result.status is ExecutionStatus.FAILED
    assert result.failure_reason is not None


def test_executor_returns_error_for_missing_variable() -> None:
    client = FakeAPIClient(APIResponse(
        status_code=200, headers={}, text="", json_body=None, duration_ms=1, url="https://example.test/booking",
    ))
    test_case = build_test_case(path_params={"booking_id": "{{missing_id}}"})

    result = APIExecutor(client).execute(test_case)  # type: ignore[arg-type]

    assert result.status is ExecutionStatus.ERROR
    assert "missing_id" in (result.failure_reason or "")
