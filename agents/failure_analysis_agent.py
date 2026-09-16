"""Evidence-oriented AI classification of deterministic execution failures."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence

from ai.failure_analyzer import is_failure_result
from ai.llm_client import LLMClient
from clients.api_client import mask_sensitive_text
from models.execution_models import ExecutionResult
from models.failure_analysis import FailureAnalysis
from models.test_case import TestCase


class FailureAnalysisError(ValueError):
    """Raised when analysis is requested for a non-failure or mismatched result."""


class FailureAnalysisAgent:
    """Classify failures while preserving the distinction between evidence and assumptions."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client
        self._cache: dict[str, FailureAnalysis] = {}

    def analyze_failure(
        self,
        test_case: TestCase,
        execution_result: ExecutionResult,
        *,
        logs: Sequence[str] = (),
        force_refresh: bool = False,
    ) -> FailureAnalysis:
        """Return a validated non-conclusive classification for one failed execution."""
        if execution_result.test_id != test_case.id:
            raise FailureAnalysisError("Execution result test ID does not match the supplied test case.")
        if not is_failure_result(execution_result):
            raise FailureAnalysisError("Failure analysis is only valid for failed or error executions.")
        sanitized_logs = tuple(mask_sensitive_text(log) for log in logs)
        cache_key = self._cache_key(test_case, execution_result, sanitized_logs)
        if not force_refresh and cache_key in self._cache:
            return self._cache[cache_key]

        task = (
            "Classify this API test failure using only the supplied evidence. Do not state that an "
            "application defect is confirmed. Separate assumptions from evidence, calibrate confidence, "
            "and recommend concrete next investigation actions. If evidence is insufficient, use unknown "
            "with confidence at most 0.5.\n\n"
            f"Test case:\n{json.dumps(test_case.model_dump(), sort_keys=True)}\n\n"
            f"Execution result:\n{json.dumps(execution_result.model_dump(mode='json'), sort_keys=True)}\n\n"
            f"Sanitized logs (optional):\n{json.dumps(list(sanitized_logs))}"
        )
        analysis = self._llm_client.generate_structured(task, FailureAnalysis)
        if analysis.test_id != test_case.id:
            raise FailureAnalysisError("AI analysis test ID does not match the analyzed test case.")
        self._cache[cache_key] = analysis
        return analysis

    @staticmethod
    def _cache_key(
        test_case: TestCase, execution_result: ExecutionResult, logs: Sequence[str]
    ) -> str:
        payload = {
            "test_case": test_case.model_dump(mode="json"),
            "execution_result": execution_result.model_dump(mode="json"),
            "logs": list(logs),
        }
        serialized = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
