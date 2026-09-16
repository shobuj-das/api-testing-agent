"""Extensible deterministic assertions over captured HTTP responses."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from jsonschema import ValidationError as JsonSchemaValidationError
from jsonschema import validate as validate_json_schema

from clients.api_client import APIResponse
from models.execution_models import AssertionResult
from models.test_case import Assertion, AssertionType


class AssertionEngine:
    """Evaluate declared assertions without involving an LLM."""

    def evaluate(self, response: APIResponse, assertions: list[Assertion]) -> list[AssertionResult]:
        """Evaluate every assertion, retaining failures instead of failing fast."""
        return [self._evaluate_one(response, assertion) for assertion in assertions]

    def _evaluate_one(self, response: APIResponse, assertion: Assertion) -> AssertionResult:
        try:
            passed, message = self._assert(response, assertion)
        except (KeyError, TypeError, ValueError, JsonSchemaValidationError) as exc:
            passed, message = False, f"Assertion could not be evaluated: {exc}"
        return AssertionResult(
            assertion_type=assertion.assertion_type.value, passed=passed, message=message,
        )

    def _assert(self, response: APIResponse, assertion: Assertion) -> tuple[bool, str]:
        kind = assertion.assertion_type
        if kind is AssertionType.STATUS_CODE_EQUALS:
            return self._equals("status code", response.status_code, assertion.expected)
        if kind is AssertionType.STATUS_CODE_IN:
            expected = assertion.expected
            if not isinstance(expected, list):
                raise ValueError("status_code_in expected value must be a list.")
            passed = response.status_code in expected
            return passed, f"Expected status code in {expected}; actual {response.status_code}."
        if kind in {AssertionType.RESPONSE_CONTAINS_FIELD, AssertionType.RESPONSE_FIELD_EXISTS}:
            self._get_json_path(response.json_body, self._target(assertion))
            return True, f"Response field '{assertion.target}' exists."
        if kind is AssertionType.RESPONSE_FIELD_EQUALS:
            actual = self._get_json_path(response.json_body, self._target(assertion))
            return self._equals(f"response field '{assertion.target}'", actual, assertion.expected)
        if kind is AssertionType.RESPONSE_FIELD_TYPE:
            actual = self._get_json_path(response.json_body, self._target(assertion))
            expected_type = assertion.expected
            if not isinstance(expected_type, str):
                raise ValueError("response_field_type expected value must be a string.")
            passed = self._matches_json_type(actual, expected_type)
            return passed, (
                f"Expected response field '{assertion.target}' type {expected_type}; "
                f"actual {type(actual).__name__}."
            )
        if kind is AssertionType.JSON_SCHEMA:
            if not isinstance(assertion.expected, Mapping):
                raise ValueError("json_schema expected value must be an object.")
            validate_json_schema(instance=response.json_body, schema=dict(assertion.expected))
            return True, "Response matches JSON Schema."
        if kind is AssertionType.RESPONSE_HEADER_EXISTS:
            self._get_header(response.headers, self._target(assertion))
            return True, f"Response header '{assertion.target}' exists."
        if kind is AssertionType.RESPONSE_HEADER_EQUALS:
            actual = self._get_header(response.headers, self._target(assertion))
            return self._equals(f"response header '{assertion.target}'", actual, assertion.expected)
        if kind is AssertionType.RESPONSE_TIME_MAX_MS:
            if not isinstance(assertion.expected, (int, float)) or isinstance(assertion.expected, bool):
                raise ValueError("response_time_max_ms expected value must be numeric.")
            passed = response.duration_ms <= assertion.expected
            return passed, f"Expected response time <= {assertion.expected}ms; actual {response.duration_ms:.2f}ms."
        raise ValueError(f"Unsupported assertion type: {kind}")

    @staticmethod
    def _equals(label: str, actual: Any, expected: Any) -> tuple[bool, str]:
        return actual == expected, f"Expected {label} {expected!r}; actual {actual!r}."

    @staticmethod
    def _target(assertion: Assertion) -> str:
        if not assertion.target:
            raise ValueError("Assertion target is missing.")
        return assertion.target

    @staticmethod
    def _get_header(headers: Mapping[str, str], target: str) -> str:
        for name, value in headers.items():
            if name.lower() == target.lower():
                return value
        raise KeyError(f"Header '{target}' was not present.")

    @classmethod
    def _get_json_path(cls, payload: Any, path: str) -> Any:
        current = payload
        for part in path.split("."):
            if isinstance(current, Mapping):
                if part not in current:
                    raise KeyError(f"Field '{path}' was not present.")
                current = current[part]
                continue
            if isinstance(current, list) and part.isdigit():
                index = int(part)
                if index >= len(current):
                    raise KeyError(f"List index '{path}' was not present.")
                current = current[index]
                continue
            raise KeyError(f"Field '{path}' was not present.")
        return current

    @staticmethod
    def _matches_json_type(value: Any, expected_type: str) -> bool:
        type_checks = {
            "object": lambda item: isinstance(item, dict),
            "array": lambda item: isinstance(item, list),
            "string": lambda item: isinstance(item, str),
            "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
            "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
            "boolean": lambda item: isinstance(item, bool),
            "null": lambda item: item is None,
        }
        if expected_type not in type_checks:
            raise ValueError(f"Unsupported JSON type '{expected_type}'.")
        return type_checks[expected_type](value)
