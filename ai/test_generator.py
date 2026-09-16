"""Deterministic validation helpers for structured AI-generated test cases."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from models.api_models import APIEndpoint
from models.test_case import TestCase


def _normalized_value(value: Any) -> str:
    """Produce a stable signature for JSON-like request conditions."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def test_signature(test_case: TestCase) -> tuple[str, ...]:
    """Identify a logical test by request condition and expected behavior, not its wording."""
    assertion_signature = _normalized_value([
        {
            "type": assertion.assertion_type.value,
            "target": assertion.target,
            "expected": assertion.expected,
        }
        for assertion in test_case.assertions
    ])
    return (
        test_case.method.value,
        test_case.endpoint,
        _normalized_value(test_case.headers),
        _normalized_value(test_case.query_params),
        _normalized_value(test_case.path_params),
        _normalized_value(test_case.request_body),
        str(test_case.expected_status),
        assertion_signature,
    )


class TestDeduplicator:
    """Remove equivalent test conditions without depending on generated titles."""

    def remove_duplicates(self, test_cases: list[TestCase]) -> tuple[list[TestCase], int]:
        seen: set[tuple[str, ...]] = set()
        unique: list[TestCase] = []
        removed = 0
        for test_case in test_cases:
            signature = test_signature(test_case)
            if signature in seen:
                removed += 1
                continue
            seen.add(signature)
            unique.append(test_case)
        return unique, removed


class TestPrioritizer:
    """Order tests using a transparent deterministic risk policy."""

    def reasons(self, test_case: TestCase, endpoint: APIEndpoint) -> tuple[str, ...]:
        reasons: list[str] = []
        if test_case.method.value == "DELETE":
            reasons.append("destructive operation")
        if test_case.category.value == "workflow":
            reasons.append("workflow dependency")
        if endpoint.authentication_required:
            reasons.append("authentication dependency")
        if test_case.category.value == "negative":
            reasons.append("negative scenario")
        if test_case.category.value == "boundary":
            reasons.append("boundary scenario")
        if not reasons:
            reasons.append("declared test priority")
        return tuple(reasons)

    def sort(self, test_cases: list[TestCase], endpoint: APIEndpoint) -> list[TestCase]:
        return sorted(test_cases, key=lambda item: (self._risk_rank(item, endpoint), item.id))

    def _risk_rank(self, test_case: TestCase, endpoint: APIEndpoint) -> int:
        if test_case.method.value == "DELETE":
            return 0
        if test_case.category.value == "workflow":
            return 1
        if endpoint.authentication_required:
            return 2
        if test_case.category.value == "negative":
            return 3
        if test_case.category.value == "boundary":
            return 4
        priority_rank = {"critical": 5, "high": 6, "medium": 7, "low": 8}
        return priority_rank[test_case.priority.value]


@dataclass(frozen=True, slots=True)
class TestGenerationResult:
    """Validated, deduplicated and ordered generation output for downstream execution."""

    test_cases: tuple[TestCase, ...]
    reasoning_summary: str
    evidence: tuple[str, ...]
    duplicates_removed: int
    prioritization_reasons: dict[str, tuple[str, ...]]
