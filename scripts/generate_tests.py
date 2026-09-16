"""CLI tool to generate, deduplicate and prioritize API test cases from an OpenAPI spec."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Ensure project root is on sys.path for direct execution
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.api_understanding_agent import APIUnderstandingAgent
from agents.test_generation_agent import TestGenerationAgent
from ai.auto_mock_client import AutoMockLLMClient
from config.project_config import ProjectConfig
from config.settings import Settings
from models.test_plan import TestPlan
from openapi.parser import OpenAPIParser
from scripts.analyze_api import fetch_spec_document
from test_data.test_storage import save_generated_tests


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate declarative test cases from an OpenAPI 3 specification.")
    parser.add_argument("--spec", help="Path or URL to OpenAPI 3 JSON/YAML file.")
    parser.add_argument("--spec-url", help="URL to remote OpenAPI 3 specification.")
    parser.add_argument("--config", help="Optional project config file (YAML/JSON).")
    parser.add_argument("--max-tests", type=int, default=50, help="Maximum number of test cases to generate.")
    parser.add_argument("--category", help="Filter generated tests by category (e.g. functional, negative).")
    parser.add_argument("--endpoint", help="Filter generated tests by endpoint path substring.")
    parser.add_argument("--output", default="test_data/generated/generated_tests.json", help="Path to save generated tests JSON.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output.")

    args = parser.parse_args()

    spec_source = args.spec or args.spec_url
    if args.config:
        cfg = ProjectConfig.from_file(args.config)
        spec_source = spec_source or cfg.spec_path or cfg.spec_url

    if not spec_source:
        print("Error: Specify an OpenAPI spec with --spec <file_or_url> or --config <file>", file=sys.stderr)
        return 1

    try:
        doc = fetch_spec_document(spec_source)
        openapi_parser = OpenAPIParser()
        spec = openapi_parser.parse_document(doc)
    except Exception as exc:
        print(f"Error parsing OpenAPI specification: {exc}", file=sys.stderr)
        return 1

    print("=" * 65)
    print(f" GENERATING TESTS: {spec.title} (v{spec.version})")
    print("=" * 65)

    llm_client = AutoMockLLMClient()
    understanding_agent = APIUnderstandingAgent(llm_client)
    generation_agent = TestGenerationAgent(llm_client)

    all_tests = []
    endpoint_capacity = max(1, args.max_tests // max(1, len(spec.endpoints)))

    for endpoint in spec.endpoints:
        if args.endpoint and args.endpoint.lower() not in endpoint.path.lower():
            continue
        if len(all_tests) >= args.max_tests:
            break

        understanding = understanding_agent.understand_endpoint(endpoint)
        remaining = args.max_tests - len(all_tests)
        limit = min(endpoint_capacity, remaining)

        batch_result = generation_agent.generate_for_endpoint(endpoint, understanding, max_tests=limit)
        for tc in batch_result.test_cases:
            if args.category and tc.category.value.lower() != args.category.lower():
                continue
            all_tests.append(tc)

    plan = TestPlan(
        name=f"{spec.title} Generated Test Suite",
        objective=f"Automated test suite for {spec.title}",
        test_cases=all_tests,
        reasoning_summary=f"Generated {len(all_tests)} tests across {len(spec.endpoints)} endpoints.",
        source="agent_cli",
    )

    out_path = save_generated_tests(all_tests, destination=args.output, plan=plan)

    print(f"\nSuccessfully generated {len(all_tests)} test cases!")
    print(f"Saved to: {out_path}\n")

    print(f"{'ID':<30} {'METHOD':<8} {'ENDPOINT':<25} {'CATEGORY':<12} {'PRIORITY'}")
    print("-" * 85)
    for tc in all_tests:
        print(f"{tc.id:<30} {tc.method.value:<8} {tc.endpoint:<25} {tc.category.value:<12} {tc.priority.value}")
    print("=" * 85)

    return 0


if __name__ == "__main__":
    sys.exit(main())
