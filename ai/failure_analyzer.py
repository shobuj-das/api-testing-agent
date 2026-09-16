"""Deterministic helpers for deciding whether failure analysis is appropriate."""

from __future__ import annotations

from models.execution_models import ExecutionResult, ExecutionStatus


def is_failure_result(result: ExecutionResult) -> bool:
    """Only failed/error executions should consume an LLM failure-analysis call."""
    return result.status in {ExecutionStatus.FAILED, ExecutionStatus.ERROR}
