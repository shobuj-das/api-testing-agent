"""Generate validated, declarative API tests from endpoint understanding records."""

from __future__ import annotations

import json

from ai.llm_client import LLMClient
from ai.test_generator import TestDeduplicator, TestGenerationResult, TestPrioritizer
from models.api_models import APIEndpoint
from models.api_understanding import EndpointUnderstanding
from models.test_generation import GeneratedTestBatch


class TestGenerationError(ValueError):
    """Raised when generated tests conflict with their requested endpoint or limits."""


class TestGenerationAgent:
    """Turn evidence-based endpoint understanding into safe structured test definitions."""

    def __init__(
        self,
        llm_client: LLMClient,
        deduplicator: TestDeduplicator | None = None,
        prioritizer: TestPrioritizer | None = None,
    ) -> None:
        self._llm_client = llm_client
        self._deduplicator = deduplicator or TestDeduplicator()
        self._prioritizer = prioritizer or TestPrioritizer()

    def generate_for_endpoint(
        self,
        endpoint: APIEndpoint,
        understanding: EndpointUnderstanding,
        *,
        max_tests: int = 20,
    ) -> TestGenerationResult:
        """Generate and validate a bounded useful test set for exactly one endpoint."""
        if max_tests <= 0:
            raise ValueError("max_tests must be positive.")
        if understanding.method.upper() != endpoint.method.value or understanding.path != endpoint.path:
            raise TestGenerationError("Endpoint understanding does not belong to the requested endpoint.")
        task = (
            "Generate a concise, high-value set of declarative API tests for this endpoint. "
            f"Generate no more than {max_tests} cases. Cover supported functional, negative, and "
            "boundary scenarios, plus contract or workflow cases when evidence supports them. Do not "
            "generate Python, shell commands, or unsupported combinations. Every test must target the "
            "same method and relative endpoint given below.\n\n"
            f"Endpoint:\n{json.dumps(endpoint.model_dump(by_alias=True), sort_keys=True)}\n\n"
            f"Understanding:\n{json.dumps(understanding.model_dump(), sort_keys=True)}"
        )
        batch = self._llm_client.generate_structured(task, GeneratedTestBatch)
        if len(batch.test_cases) > max_tests:
            raise TestGenerationError(f"AI returned {len(batch.test_cases)} tests; limit is {max_tests}.")
        self._validate_test_scope(batch, endpoint)
        unique_cases, duplicates_removed = self._deduplicator.remove_duplicates(batch.test_cases)
        ordered_cases = self._prioritizer.sort(unique_cases, endpoint)
        return TestGenerationResult(
            test_cases=tuple(ordered_cases), reasoning_summary=batch.reasoning_summary,
            evidence=tuple(batch.evidence), duplicates_removed=duplicates_removed,
            prioritization_reasons={
                test_case.id: self._prioritizer.reasons(test_case, endpoint)
                for test_case in ordered_cases
            },
        )

    @staticmethod
    def _validate_test_scope(batch: GeneratedTestBatch, endpoint: APIEndpoint) -> None:
        seen_ids: set[str] = set()
        for test_case in batch.test_cases:
            if test_case.id in seen_ids:
                raise TestGenerationError(f"AI returned duplicate test ID: {test_case.id}")
            seen_ids.add(test_case.id)
            if test_case.method != endpoint.method or test_case.endpoint != endpoint.path:
                raise TestGenerationError(
                    f"Test '{test_case.id}' targets {test_case.method} {test_case.endpoint}, "
                    f"not {endpoint.method} {endpoint.path}."
                )
