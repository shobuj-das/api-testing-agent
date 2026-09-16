"""Master CLI entrypoint for running the bounded AI API Testing Agent."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure project root is on sys.path for direct execution
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.api_understanding_agent import APIUnderstandingAgent
from agents.failure_analysis_agent import FailureAnalysisAgent
from agents.orchestrator import AgentOrchestrator
from agents.test_generation_agent import TestGenerationAgent
from agents.workflow_builder import WorkflowBuilder
from ai.auto_mock_client import AutoMockLLMClient
from clients.api_client import APIClient
from config.project_config import ProjectConfig
from config.settings import Environment, Settings
from executor.api_executor import APIExecutor
from executor.workflow_executor import WorkflowExecutor
from models.agent_state import AgentAction
from models.execution_models import ExecutionStatus
from models.test_case import TestCase
from openapi.dependency_detector import DependencyDetector
from openapi.parser import OpenAPIParser
from reports.report_generator import ReportGenerator
from scripts.analyze_api import fetch_spec_document
from test_data.test_storage import save_generated_tests


def print_banner() -> None:
    print("\n" + "=" * 70)
    print("       AI API TESTING AGENT - AUTONOMOUS EXPLORATORY QA")
    print("=" * 70)


def format_test_table(test_cases: list[TestCase]) -> str:
    lines = [
        f"{'ID':<30} {'METHOD':<8} {'ENDPOINT':<22} {'CATEGORY':<12} {'PRIORITY'}",
        "-" * 80,
    ]
    for tc in test_cases:
        lines.append(f"{tc.id:<30} {tc.method.value:<8} {tc.endpoint:<22} {tc.category.value:<12} {tc.priority.value}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the AI API Testing Agent on any OpenAPI specification.")
    parser.add_argument("--spec", help="Path or URL to OpenAPI 3 JSON/YAML file.")
    parser.add_argument("--spec-url", help="URL to remote OpenAPI 3 specification.")
    parser.add_argument("--config", help="Optional project config file (YAML/JSON).")
    parser.add_argument("--base-url", help="Override API target base URL.")
    parser.add_argument("--environment", choices=["local", "dev", "staging", "production"], default="staging", help="Target environment.")
    parser.add_argument("--allow-production", action="store_true", help="Explicitly enable production execution.")
    parser.add_argument("--max-tests", type=int, default=30, help="Maximum number of tests to generate.")
    parser.add_argument("--max-iterations", type=int, default=50, help="Maximum agent loop iterations.")
    parser.add_argument("--max-retries", type=int, default=1, help="Maximum retries for transient failures.")
    parser.add_argument("--category", help="Filter tests by category (e.g. functional, negative).")
    parser.add_argument("--endpoint", help="Filter tests by endpoint path substring.")
    parser.add_argument("--auto-approve", "-y", action="store_true", help="Skip human approval prompt and execute tests autonomously.")
    parser.add_argument("--workflows", dest="enable_workflows", action="store_true", default=True, help="Enable multi-step workflow execution (default).")
    parser.add_argument("--no-workflows", dest="enable_workflows", action="store_false", help="Disable multi-step workflow execution.")
    parser.add_argument("--report-dir", default="reports", help="Directory for JSON and HTML reports.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output.")

    args = parser.parse_args()

    print_banner()

    # Load configuration from file if provided, then overlay CLI flags
    project_cfg = ProjectConfig()
    if args.config:
        try:
            project_cfg = ProjectConfig.from_file(args.config)
            print(f"[CONFIG] Loaded configuration from {args.config} for project '{project_cfg.project_name}'")
        except Exception as exc:
            print(f"Error reading configuration file: {exc}", file=sys.stderr)
            return 1

    spec_source = args.spec or args.spec_url or project_cfg.spec_path or project_cfg.spec_url
    if not spec_source:
        print("Error: Please provide an OpenAPI specification via --spec <file_or_url> or --config <file>.", file=sys.stderr)
        return 1

    # 1. Parse OpenAPI Specification
    print(f"\n[1/5] Ingesting OpenAPI Specification: {spec_source}")
    try:
        doc = fetch_spec_document(spec_source)
        openapi_parser = OpenAPIParser()
        spec = openapi_parser.parse_document(doc)
        print(f"      Parsed API '{spec.title}' (v{spec.version}) with {len(spec.endpoints)} operations.")
    except Exception as exc:
        print(f"Error parsing specification: {exc}", file=sys.stderr)
        return 1

    # Filter endpoints if requested
    if args.endpoint:
        spec.endpoints = [ep for ep in spec.endpoints if args.endpoint.lower() in ep.path.lower()]
        print(f"      Filtered to {len(spec.endpoints)} operations matching '{args.endpoint}'.")

    # Determine Base URL
    base_url = args.base_url or project_cfg.base_url or (spec.servers[0] if spec.servers else "http://localhost:8000")
    env = Environment(args.environment.lower())
    allow_prod = args.allow_production or project_cfg.allow_production_execution

    settings = Settings(
        api_base_url=base_url.rstrip("/"),
        environment=env,
        allow_production_execution=allow_prod,
        api_timeout=project_cfg.api_timeout,
        max_agent_iterations=args.max_iterations,
        max_retries=args.max_retries,
    )

    print(f"      Target Base URL: {settings.api_base_url} ({settings.environment.value.upper()})")

    # 2. Plan and Understand Endpoints
    print("\n[2/5] Running API Understanding and Test Generation Agents...")
    llm_client = AutoMockLLMClient()
    understanding_agent = APIUnderstandingAgent(llm_client)
    generation_agent = TestGenerationAgent(llm_client)
    failure_agent = FailureAnalysisAgent(llm_client)

    api_client = APIClient(settings)
    api_executor = APIExecutor(api_client)
    workflow_executor = WorkflowExecutor(api_executor)
    dependency_detector = DependencyDetector()
    workflow_builder = WorkflowBuilder()

    orchestrator = AgentOrchestrator(
        understanding_agent=understanding_agent,
        generation_agent=generation_agent,
        executor=api_executor,
        failure_agent=failure_agent,
        workflow_executor=workflow_executor,
        dependency_detector=dependency_detector,
        workflow_builder=workflow_builder,
        enable_workflows=args.enable_workflows,
        max_iterations=args.max_iterations,
        max_retries=args.max_retries,
        max_generated_tests=args.max_tests,
    )

    # First generate the understandings to present tests to the user
    understandings = understanding_agent.understand_specification(spec)
    all_generated: list[TestCase] = []
    endpoint_capacity = max(1, args.max_tests // max(1, len(spec.endpoints)))

    for ep, und in zip(spec.endpoints, understandings, strict=False):
        remaining = args.max_tests - len(all_generated)
        if remaining <= 0:
            break
        limit = min(endpoint_capacity, remaining)
        res = generation_agent.generate_for_endpoint(ep, und, max_tests=limit)
        for tc in res.test_cases:
            if args.category and tc.category.value.lower() != args.category.lower():
                continue
            all_generated.append(tc)

    save_generated_tests(all_generated)
    print(f"      Generated {len(all_generated)} validated, deduplicated test cases.")

    # 3. Human Approval Gate
    print("\n[3/5] Test Plan Review & Human Approval Mode:")
    print(format_test_table(all_generated))

    auto_approved = args.auto_approve or project_cfg.auto_approve
    if not auto_approved:
        try:
            choice = input(f"\nExecute these {len(all_generated)} tests against {settings.api_base_url}? [Y/n]: ").strip().lower()
            if choice in {"n", "no"}:
                print("Execution aborted by user. Tests remain saved in test_data/generated/generated_tests.json.")
                return 0
        except (EOFError, KeyboardInterrupt):
            print("\nExecution skipped.")
            return 0
    else:
        print("\n      [AUTO-APPROVE] Autonomous execution enabled; proceeding to execution.")

    # 4. Deterministic Execution & Failure Analysis
    print("\n[4/5] Executing Tests Deterministically...")
    state = orchestrator.run(spec)

    print(f"\n      Executed {len(state.execution_results)} tests.")
    passed_count = sum(1 for r in state.execution_results if r.status is ExecutionStatus.PASSED)
    failed_count = sum(1 for r in state.execution_results if r.status is ExecutionStatus.FAILED)
    error_count = sum(1 for r in state.execution_results if r.status is ExecutionStatus.ERROR)

    for r in state.execution_results:
        badge = "PASSED" if r.status is ExecutionStatus.PASSED else "FAILED"
        color_code = "PASS" if r.status is ExecutionStatus.PASSED else "FAIL"
        detail = f" - {r.failure_reason}" if r.failure_reason else ""
        print(f"      [{color_code}] {r.test_id:<32} ({r.duration_ms:.1f}ms): {badge}{detail}")

    if state.failures:
        print(f"\n      AI Failure Analysis ({len(state.failures)} classified):")
        for f in state.failures:
            print(f"      * {f.test_id}: {f.classification} (confidence: {f.confidence*100:.0f}%) -> {f.conclusion}")

    if state.workflow_results:
        print(f"\n      Workflow Executions ({len(state.workflow_results)}):")
        for wf in state.workflow_results:
            wf_status = "PASSED" if wf.get("passed") else "FAILED"
            print(f"      * {wf.get('workflow_name')}: {wf_status} ({len(wf.get('step_results', []))} steps)")

    # 5. Report Generation
    print("\n[5/5] Generating QA Reports...")
    reporter = ReportGenerator(report_dir=args.report_dir)
    json_path, html_path = reporter.generate(state)

    pass_rate = (passed_count / len(state.execution_results) * 100) if state.execution_results else 0.0

    print("\n" + "=" * 70)
    print("                    QA RUN SUMMARY")
    print("=" * 70)
    print(f" Total Executed : {len(state.execution_results)}")
    print(f" Passed         : {passed_count}")
    print(f" Failed         : {failed_count}")
    print(f" Errors         : {error_count}")
    print(f" Pass Rate      : {pass_rate:.1f}%")
    print(f" Workflows Run  : {len(state.workflow_results)}")
    print("-" * 70)
    print(f" JSON Report    : {json_path}")
    print(f" HTML Report    : {html_path}")
    print("=" * 70 + "\n")

    return 0 if (failed_count == 0 and error_count == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
