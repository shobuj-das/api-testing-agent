"""Storage and retrieval helpers for generated API test cases."""

from __future__ import annotations

import json
from pathlib import Path

from models.test_case import TestCase
from models.test_plan import TestPlan

DEFAULT_STORAGE_PATH = Path("test_data/generated/generated_tests.json")


def save_generated_tests(
    tests: list[TestCase],
    destination: str | Path = DEFAULT_STORAGE_PATH,
    plan: TestPlan | None = None,
) -> Path:
    """Save generated test cases and optional plan to a structured JSON file."""
    dest_path = Path(destination)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "count": len(tests),
        "test_cases": [test.model_dump(mode="json") for test in tests],
        "plan": plan.model_dump(mode="json") if plan else None,
    }
    dest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return dest_path


def load_generated_tests(source: str | Path = DEFAULT_STORAGE_PATH) -> list[TestCase]:
    """Load test cases from a stored JSON file."""
    src_path = Path(source)
    if not src_path.exists():
        raise FileNotFoundError(f"Generated test file not found: {src_path}")
    data = json.loads(src_path.read_text(encoding="utf-8"))
    raw_tests = data.get("test_cases", [])
    return [TestCase.model_validate_json(json.dumps(item)) for item in raw_tests]
