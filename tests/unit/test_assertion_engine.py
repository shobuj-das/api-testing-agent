"""Tests for deterministic response assertion behavior."""

from clients.api_client import APIResponse
from executor.assertion_engine import AssertionEngine
from models.test_case import Assertion, AssertionType


RESPONSE = APIResponse(
    status_code=200, headers={"Content-Type": "application/json", "X-Request-ID": "abc"},
    text='{"booking": {"id": 7}}', json_body={"booking": {"id": 7}},
    duration_ms=12.5, url="https://example.test/booking/7",
)


def test_assertion_engine_supports_nested_fields_headers_types_and_schema() -> None:
    results = AssertionEngine().evaluate(RESPONSE, [
        Assertion(assertion_type=AssertionType.STATUS_CODE_IN, expected=[200, 201]),
        Assertion(assertion_type=AssertionType.RESPONSE_FIELD_EQUALS, target="booking.id", expected=7),
        Assertion(assertion_type=AssertionType.RESPONSE_FIELD_TYPE, target="booking.id", expected="integer"),
        Assertion(assertion_type=AssertionType.RESPONSE_HEADER_EQUALS, target="content-type", expected="application/json"),
        Assertion(assertion_type=AssertionType.JSON_SCHEMA, expected={
            "type": "object", "required": ["booking"],
            "properties": {"booking": {"type": "object", "required": ["id"]}},
        }),
    ])

    assert all(result.passed for result in results)


def test_assertion_engine_records_failure_without_raising() -> None:
    results = AssertionEngine().evaluate(RESPONSE, [
        Assertion(assertion_type=AssertionType.RESPONSE_FIELD_EXISTS, target="booking.missing"),
        Assertion(assertion_type=AssertionType.RESPONSE_TIME_MAX_MS, expected=10),
    ])

    assert [result.passed for result in results] == [False, False]
    assert "not present" in results[0].message
