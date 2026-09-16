"""Deterministic execution of dependent multi-step API workflows."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from clients.api_client import APIResponse, mask_sensitive
from executor.api_executor import APIExecutor
from models.dependency import VariableSourceLocation
from models.execution_models import ExecutionStatus, ResponseRecord
from models.workflow import (
    StepExecutionResult,
    VariableExtractionRule,
    Workflow,
    WorkflowExecutionResult,
    WorkflowStep,
)


class WorkflowExecutionError(RuntimeError):
    """Raised when an unrecoverable error occurs during workflow execution."""


def _extract_from_dict(data: Any, path: str) -> Any:
    """Extract a value from nested dicts/lists using dot or bracket notation."""
    if data is None:
        return None
    # Normalize paths like "items[0].id" to "items.0.id"
    normalized_path = re.sub(r"\[(\d+)\]", r".\1", path)
    tokens = [t for t in normalized_path.split(".") if t]

    current: Any = data
    for token in tokens:
        if isinstance(current, Mapping):
            if token not in current:
                return None
            current = current[token]
        elif isinstance(current, (list, tuple)):
            try:
                index = int(token)
                if 0 <= index < len(current):
                    current = current[index]
                else:
                    return None
            except ValueError:
                return None
        else:
            return None
    return current


def _extract_variable(
    rule: VariableExtractionRule,
    raw_response: APIResponse | None,
    response_record: ResponseRecord | None,
) -> Any:
    """Extract unmasked variable from APIResponse (or fallback to ResponseRecord)."""
    body = raw_response.json_body if (raw_response and raw_response.json_body is not None) else (response_record.body if response_record else None)
    headers = raw_response.headers if raw_response else (response_record.headers if response_record else {})

    if body is None and not headers:
        if rule.required:
            raise WorkflowExecutionError(
                f"Cannot extract variable '{rule.variable_name}': response was empty."
            )
        return rule.default

    if rule.source is VariableSourceLocation.BODY:
        val = _extract_from_dict(body, rule.field_path)
        if val is None:
            if rule.required:
                raise WorkflowExecutionError(
                    f"Required variable '{rule.variable_name}' not found at path '{rule.field_path}' in response body."
                )
            return rule.default
        return val

    if rule.source is VariableSourceLocation.HEADER:
        headers_lower = {k.lower(): v for k, v in headers.items()}
        val = headers_lower.get(rule.field_path.lower())
        if val is None:
            if rule.required:
                raise WorkflowExecutionError(
                    f"Required variable '{rule.variable_name}' not found in response header '{rule.field_path}'."
                )
            return rule.default
        return val

    return rule.default


class WorkflowExecutor:
    """Executes workflows sequentially with dynamic variable propagation and cleanup handling."""

    def __init__(self, api_executor: APIExecutor) -> None:
        self._api_executor = api_executor

    def execute(
        self,
        workflow: Workflow,
        *,
        variables: Mapping[str, Any] | None = None,
    ) -> WorkflowExecutionResult:
        """Execute a workflow step by step, extracting variables and respecting cleanup."""
        context_vars: dict[str, Any] = dict(workflow.initial_variables)
        if variables:
            context_vars.update(variables)

        step_results: list[StepExecutionResult] = []
        overall_passed = True
        failure_reason: str | None = None
        has_earlier_failure = False
        total_duration_ms = 0.0

        for step in workflow.steps:
            # If an earlier step failed, only run cleanup steps
            if has_earlier_failure and not step.is_cleanup:
                continue

            step_result, extracted = self._execute_step(step, context_vars)
            step_results.append(step_result)
            total_duration_ms += step_result.execution_result.duration_ms

            if step_result.passed:
                context_vars.update(extracted)
            else:
                if not step.continue_on_failure and not has_earlier_failure:
                    overall_passed = False
                    has_earlier_failure = True
                    failure_reason = (
                        f"Step '{step.name}' ({step.step_id}) failed: "
                        f"{step_result.execution_result.failure_reason}"
                    )

        if has_earlier_failure:
            overall_passed = False

        return WorkflowExecutionResult(
            workflow_id=workflow.id,
            workflow_name=workflow.name,
            passed=overall_passed,
            step_results=step_results,
            final_variables=mask_sensitive(context_vars),
            failure_reason=failure_reason,
            duration_ms=total_duration_ms,
        )

    def _execute_step(
        self, step: WorkflowStep, context: dict[str, Any]
    ) -> tuple[StepExecutionResult, dict[str, Any]]:
        """Run a single step, evaluate assertions, and extract variables."""
        exec_result, raw_response = self._api_executor.execute_detailed(step.test_case, variables=context)
        extracted: dict[str, Any] = {}

        if exec_result.status is not ExecutionStatus.PASSED:
            return StepExecutionResult(
                step_id=step.step_id,
                execution_result=exec_result,
                extracted_variables={},
                passed=False,
            ), {}

        # Step passed HTTP & assertion checks; extract declared variables
        try:
            for rule in step.extract_variables:
                val = _extract_variable(rule, raw_response, exec_result.response)
                extracted[rule.variable_name] = val
        except WorkflowExecutionError as exc:
            # Variable extraction failure causes step failure
            exec_result.status = ExecutionStatus.FAILED
            exec_result.failure_reason = str(exc)
            return StepExecutionResult(
                step_id=step.step_id,
                execution_result=exec_result,
                extracted_variables={},
                passed=False,
            ), {}

        return StepExecutionResult(
            step_id=step.step_id,
            execution_result=exec_result,
            extracted_variables=mask_sensitive(extracted),
            passed=True,
        ), extracted
