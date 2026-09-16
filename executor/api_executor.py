"""Deterministic execution of validated API test cases."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from clients.api_client import APIClient, APIClientError, APIResponse, mask_sensitive
from executor.assertion_engine import AssertionEngine
from models.execution_models import ExecutionResult, ExecutionStatus, RequestRecord, ResponseRecord
from models.test_case import Assertion, AssertionType, TestCase

VARIABLE_PATTERN = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}")


class VariableResolutionError(ValueError):
    """Raised if a declarative test references a missing workflow variable."""


class APIExecutor:
    """Prepare, execute, capture and assert a TestCase without AI interpretation."""

    def __init__(self, api_client: APIClient, assertion_engine: AssertionEngine | None = None) -> None:
        self._api_client = api_client
        self._assertion_engine = assertion_engine or AssertionEngine()

    def execute(
        self, test_case: TestCase, *, variables: Mapping[str, Any] | None = None
    ) -> ExecutionResult:
        """Run one validated test case and return a complete structured outcome."""
        result, _ = self.execute_detailed(test_case, variables=variables)
        return result

    def execute_detailed(
        self, test_case: TestCase, *, variables: Mapping[str, Any] | None = None
    ) -> tuple[ExecutionResult, APIResponse | None]:
        """Run test case and return both structured ExecutionResult and raw APIResponse."""
        resolved_variables = variables or {}
        try:
            resolved_endpoint = str(self._resolve_variables(test_case.endpoint, resolved_variables))
            request = self._build_request_record(test_case, resolved_variables)
            response = self._api_client.request(
                test_case.method.value, resolved_endpoint,
                headers=self._resolve_variables(test_case.headers, resolved_variables),
                query_params=self._resolve_variables(test_case.query_params, resolved_variables),
                path_params=self._resolve_variables(test_case.path_params, resolved_variables),
                json_body=self._resolve_variables(test_case.request_body, resolved_variables),
            )
        except (APIClientError, VariableResolutionError, KeyError, ValueError) as exc:
            return ExecutionResult(
                test_id=test_case.id, status=ExecutionStatus.ERROR,
                request=self._safe_request_or_none(test_case, resolved_variables),
                duration_ms=0, failure_reason=str(exc),
            ), None

        assertions = [
            Assertion(assertion_type=AssertionType.STATUS_CODE_EQUALS, expected=test_case.expected_status),
            *test_case.assertions,
        ]
        assertion_results = self._assertion_engine.evaluate(response, assertions)
        failures = [result.message for result in assertion_results if not result.passed]
        return ExecutionResult(
            test_id=test_case.id,
            status=ExecutionStatus.PASSED if not failures else ExecutionStatus.FAILED,
            request=request, response=self._response_record(response), duration_ms=response.duration_ms,
            assertions=assertion_results,
            failure_reason="; ".join(failures) if failures else None,
        ), response

    def _build_request_record(self, test_case: TestCase, variables: Mapping[str, Any]) -> RequestRecord:
        resolved_url = str(self._resolve_variables(test_case.endpoint, variables))
        return RequestRecord(
            method=test_case.method.value, url=resolved_url,
            headers=mask_sensitive(self._resolve_variables(test_case.headers, variables)),
            query_params=mask_sensitive(self._resolve_variables(test_case.query_params, variables)),
            body=mask_sensitive(self._resolve_variables(test_case.request_body, variables)),
        )

    def _safe_request_or_none(self, test_case: TestCase, variables: Mapping[str, Any]) -> RequestRecord | None:
        try:
            return self._build_request_record(test_case, variables)
        except VariableResolutionError:
            return None

    @staticmethod
    def _response_record(response: APIResponse) -> ResponseRecord:
        return ResponseRecord(
            status_code=response.status_code, headers=mask_sensitive(response.headers),
            body=mask_sensitive(response.json_body if response.json_body is not None else response.text),
        )

    def _resolve_variables(self, value: Any, variables: Mapping[str, Any]) -> Any:
        if isinstance(value, str):
            match = VARIABLE_PATTERN.fullmatch(value)
            if match:
                return self._variable_value(match.group(1), variables)
            return VARIABLE_PATTERN.sub(
                lambda item: str(self._variable_value(item.group(1), variables)), value,
            )
        if isinstance(value, list):
            return [self._resolve_variables(item, variables) for item in value]
        if isinstance(value, tuple):
            return tuple(self._resolve_variables(item, variables) for item in value)
        if isinstance(value, Mapping):
            return {key: self._resolve_variables(item, variables) for key, item in value.items()}
        return value

    @staticmethod
    def _variable_value(name: str, variables: Mapping[str, Any]) -> Any:
        if name not in variables:
            raise VariableResolutionError(f"Workflow variable '{name}' is not defined.")
        return variables[name]
