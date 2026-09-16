"""Tests for validation boundaries guarding generated test data."""

import pytest
from pydantic import ValidationError

from models.api_models import APIEndpoint, APIParameter, HTTPMethod, ParameterLocation
from models.execution_models import ExecutionResult, ExecutionStatus
from models.test_case import Assertion, AssertionType, Priority, TestCase as ApiTestCase, TestCategory as ApiTestCategory
from models.test_plan import TestPlan as ApiTestPlan


def build_test_case(**overrides: object) -> ApiTestCase:
    values: dict[str, object] = {
        "id": "booking-create-valid",
        "title": "Create a booking with valid data",
        "description": "A valid booking request returns a created resource.",
        "method": HTTPMethod.POST,
        "endpoint": "/booking",
        "expected_status": 200,
        "category": ApiTestCategory.FUNCTIONAL,
        "priority": Priority.HIGH,
        "source": "mock",
    }
    values.update(overrides)
    return ApiTestCase.model_validate(values)


def test_test_case_accepts_valid_declarative_definition() -> None:
    test_case = build_test_case(assertions=[
        Assertion(assertion_type=AssertionType.STATUS_CODE_EQUALS, expected=200),
    ])

    assert test_case.method is HTTPMethod.POST
    assert test_case.expected_status == 200


def test_test_case_rejects_unknown_ai_fields() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        build_test_case(arbitrary_python="import os")


def test_test_case_rejects_absolute_endpoint() -> None:
    with pytest.raises(ValidationError, match="relative path"):
        build_test_case(endpoint="https://unsafe.example/booking")


def test_assertion_rejects_missing_required_target() -> None:
    with pytest.raises(ValidationError, match="requires a target"):
        Assertion(assertion_type=AssertionType.RESPONSE_FIELD_EXISTS)


def test_plan_rejects_duplicate_test_ids() -> None:
    test_case = build_test_case()
    with pytest.raises(ValidationError, match="duplicate test-case IDs"):
        ApiTestPlan(
            name="Booking tests", objective="Validate booking creation",
            test_cases=[test_case, test_case], source="mock",
        )


def test_api_endpoint_validates_relative_paths_and_path_parameters() -> None:
    endpoint = APIEndpoint(
        method=HTTPMethod.GET,
        path="/booking/{booking_id}",
        parameters=[APIParameter(
            name="booking_id", location=ParameterLocation.PATH, required=True,
        )],
    )

    assert endpoint.parameters[0].name == "booking_id"


def test_execution_result_is_serializable() -> None:
    result = ExecutionResult(
        test_id="booking-create-valid", status=ExecutionStatus.PASSED, duration_ms=12.5,
    )

    assert result.model_dump(mode="json")["status"] == "passed"
