"""Unit tests for Milestone 13: Report generation."""

import json
from pathlib import Path

from models.agent_state import AgentAction, AgentDecision, AgentState
from models.api_models import APIEndpoint, APISpecification, HTTPMethod
from models.execution_models import ExecutionResult, ExecutionStatus, RequestRecord, ResponseRecord
from models.failure_analysis import FailureAnalysis, FailureCategory
from models.test_case import Priority, TestCategory as ApiTestCategory, TestCase as ApiTestCase
from reports.report_generator import ReportGenerator


def test_report_generator_creates_json_and_html(tmp_path: Path) -> None:
    spec = APISpecification(
        title="Test API",
        version="1.0",
        openapi_version="3.0.3",
        endpoints=[APIEndpoint(method=HTTPMethod.GET, path="/test")],
    )
    tc = ApiTestCase(
        id="tc-1",
        title="Test 1",
        description="Functional test",
        method=HTTPMethod.GET,
        endpoint="/test",
        expected_status=200,
        category=ApiTestCategory.FUNCTIONAL,
        priority=Priority.HIGH,
        source="test",
    )
    exec_res = ExecutionResult(
        test_id="tc-1",
        status=ExecutionStatus.PASSED,
        request=RequestRecord(method="GET", url="/test"),
        response=ResponseRecord(status_code=200, headers={}, body={"ok": True}),
        duration_ms=15.5,
    )
    state = AgentState(
        api_information=spec,
        generated_tests=[tc],
        execution_results=[exec_res],
        current_action=AgentAction.STOP,
    )

    reporter = ReportGenerator(report_dir=tmp_path)
    json_path, html_path = reporter.generate(state)

    assert json_path.exists()
    assert html_path.exists()

    # Verify JSON report structure
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["api_title"] == "Test API"
    assert data["summary"]["total_executed"] == 1
    assert data["summary"]["passed"] == 1
    assert data["summary"]["failed"] == 0
    assert data["summary"]["pass_rate_percent"] == 100.0
    assert "functional" in data["category_breakdown"]

    # Verify HTML report content
    html_text = html_path.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html_text
    assert "Test API" in html_text
    assert "Pass Rate: 100.0%" in html_text
    assert "tc-1" in html_text
