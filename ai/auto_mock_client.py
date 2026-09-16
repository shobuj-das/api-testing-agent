"""Deterministic offline LLM client for mock execution without external API keys."""

from __future__ import annotations

import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel

from ai.llm_client import LLMClient, LLMResponse
from models.api_understanding import EndpointUnderstanding, InputUnderstanding, ResponseBehavior
from models.failure_analysis import FailureAnalysis, FailureCategory
from models.test_case import Assertion, AssertionType, Priority, TestCategory, TestCase
from models.test_generation import GeneratedTestBatch

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


class AutoMockLLMClient(LLMClient):
    """Generates schema-valid, evidence-grounded data for offline CLI execution and tests."""

    def _generate(self, prompt: str, *, system_prompt: str | None = None) -> LLMResponse:
        return LLMResponse(content="{}", model="auto-mock")

    def generate_structured(
        self,
        task: str,
        response_model: type[StructuredModel],
    ) -> StructuredModel:
        """Deterministically produce schema-valid models for known agent tasks."""
        if issubclass(response_model, EndpointUnderstanding):
            data = self._mock_understanding(task)
            return response_model.model_validate_json(json.dumps(data))

        if issubclass(response_model, GeneratedTestBatch):
            data = self._mock_test_batch(task)
            return response_model.model_validate_json(json.dumps(data))

        if issubclass(response_model, FailureAnalysis):
            data = self._mock_failure_analysis(task)
            return response_model.model_validate_json(json.dumps(data))

        # Fallback to base implementation
        return super().generate_structured(task, response_model)

    def _mock_understanding(self, task: str) -> dict[str, Any]:
        """Synthesize EndpointUnderstanding from task text containing endpoint and facts."""
        ep_match = re.search(r"Endpoint metadata:\s*(\{.*?\})\s*Deterministic facts:", task, re.DOTALL)
        facts_match = re.search(r"Deterministic facts:\s*(\{.*?\})$", task, re.DOTALL)

        ep_meta = json.loads(ep_match.group(1)) if ep_match else {}
        facts = json.loads(facts_match.group(1)) if facts_match else {}

        method = ep_meta.get("method", "GET")
        path = ep_meta.get("path", "/")
        summary = ep_meta.get("summary") or f"{method} {path}"

        required_inputs = []
        for req in facts.get("required_inputs", []):
            loc, name = req.split(":", 1)
            required_inputs.append({
                "name": name, "location": loc, "data_type": "string",
                "required": True, "constraints": {},
            })

        optional_inputs = []
        for opt in facts.get("optional_inputs", []):
            loc, name = opt.split(":", 1)
            optional_inputs.append({
                "name": name, "location": loc, "data_type": "string",
                "required": False, "constraints": {},
            })

        response_behaviors = []
        for code in facts.get("documented_status_codes", ["200"]):
            response_behaviors.append({
                "status_code": str(code),
                "behavior": f"Documented response for {code}",
                "response_fields": [],
                "evidence": [f"OpenAPI response definition {code}"],
            })

        return {
            "method": method,
            "path": path,
            "purpose": summary,
            "required_inputs": required_inputs,
            "optional_inputs": optional_inputs,
            "response_behaviors": response_behaviors,
            "authentication_required": ep_meta.get("authentication_required", False),
            "dependency_hints": [],
            "negative_scenarios": ["Request with malformed input payload", "Request with invalid parameter types"],
            "boundary_conditions": ["Payload size limits", "Minimum field lengths"],
            "state_transitions": ["State unchanged or resource updated"],
            "reasoning_summary": f"Deterministic offline analysis of {method} {path}.",
            "evidence": [f"OpenAPI operation {method} {path}"],
        }

    def _mock_test_batch(self, task: str) -> dict[str, Any]:
        """Synthesize GeneratedTestBatch for the endpoint."""
        ep_match = re.search(r"Endpoint:\s*(\{.*?\})\s*Understanding:", task, re.DOTALL)
        ep = json.loads(ep_match.group(1)) if ep_match else {}

        method = ep.get("method", "GET")
        path = ep.get("path", "/")
        clean_path = re.sub(r"[^a-zA-Z0-9]+", "-", path).strip("-")

        path_params = {}
        # Fill required path params if any
        for param in ep.get("parameters", []):
            if param.get("location") == "path":
                p_name = param.get("name")
                path_params[p_name] = 1

        def _build_sample(schema: dict[str, Any]) -> Any:
            if not isinstance(schema, dict):
                return "sample"
            s_type = schema.get("type", "string")
            if s_type == "object":
                props = schema.get("properties", {})
                obj = {}
                for pk, pv in props.items():
                    if isinstance(pv, dict):
                        pt = pv.get("type", "string")
                        if pt == "object":
                            obj[pk] = _build_sample(pv)
                        elif pt == "integer":
                            obj[pk] = 100
                        elif pt == "boolean":
                            obj[pk] = True
                        elif "date" in pk.lower() or "checkin" in pk.lower():
                            obj[pk] = "2026-01-01"
                        elif "checkout" in pk.lower():
                            obj[pk] = "2026-01-05"
                        elif pk.lower() == "username":
                            obj[pk] = "admin"
                        elif pk.lower() == "password":
                            obj[pk] = "password123"
                        else:
                            obj[pk] = f"sample_{pk}"
                return obj
            elif s_type == "integer":
                return 100
            elif s_type == "boolean":
                return True
            return "sample"

        request_body = None
        if ep.get("request_body_schema"):
            request_body = _build_sample(ep["request_body_schema"])

        # Generate Functional Test
        test_cases = [
            {
                "id": f"{method.lower()}-{clean_path}-happy",
                "title": f"Valid {method} {path}",
                "description": f"Verify successful {method} {path} response.",
                "method": method,
                "endpoint": path,
                "headers": {},
                "query_params": {},
                "path_params": path_params,
                "request_body": request_body,
                "expected_status": 200 if method in {"GET", "PUT", "PATCH"} else (201 if method == "POST" and "201" in [r.get("status_code") for r in ep.get("responses", [])] else 200),
                "expected_response_fields": [],
                "assertions": [
                    {
                        "assertion_type": AssertionType.STATUS_CODE_EQUALS.value,
                        "expected": 200 if method in {"GET", "PUT", "PATCH"} else (201 if method == "POST" and "201" in [r.get("status_code") for r in ep.get("responses", [])] else 200),
                    }
                ],
                "category": TestCategory.FUNCTIONAL.value,
                "priority": Priority.HIGH.value,
                "source": "auto_mock",
            }
        ]

        # Generate Negative Test
        if path_params or request_body:
            neg_path_params = {k: 999999 for k in path_params}
            test_cases.append({
                "id": f"{method.lower()}-{clean_path}-neg-notfound",
                "title": f"Negative {method} {path}",
                "description": f"Verify rejected or 404 response for invalid target in {method} {path}.",
                "method": method,
                "endpoint": path,
                "headers": {},
                "query_params": {},
                "path_params": neg_path_params,
                "request_body": None if request_body is None else {},
                "expected_status": 404 if path_params else 400,
                "expected_response_fields": [],
                "assertions": [
                    {
                        "assertion_type": AssertionType.STATUS_CODE_IN.value,
                        "expected": [400, 404, 422, 500],
                    }
                ],
                "category": TestCategory.NEGATIVE.value,
                "priority": Priority.MEDIUM.value,
                "source": "auto_mock",
            })

        return {
            "test_cases": test_cases,
            "reasoning_summary": f"Generated baseline tests for {method} {path}.",
            "evidence": [f"OpenAPI endpoint {method} {path}"],
        }

    def _mock_failure_analysis(self, task: str) -> dict[str, Any]:
        """Synthesize FailureAnalysis from test case and execution result."""
        tc_match = re.search(r"Test case:\s*(\{.*?\})\s*Execution result:", task, re.DOTALL)
        exec_match = re.search(r"Execution result:\s*(\{.*?\})\s*Sanitized logs", task, re.DOTALL)

        tc = json.loads(tc_match.group(1)) if tc_match else {}
        exec_res = json.loads(exec_match.group(1)) if exec_match else {}

        test_id = tc.get("id", "test-case")
        failure_reason = exec_res.get("failure_reason") or "Assertion failed"

        # Calibration
        if "401" in failure_reason or "403" in failure_reason:
            classification = FailureCategory.AUTHENTICATION_ISSUE.value
            conf = 0.85
        elif "timeout" in failure_reason.lower() or "connect" in failure_reason.lower():
            classification = FailureCategory.TIMEOUT.value
            conf = 0.80
        elif "404" in failure_reason:
            classification = FailureCategory.INVALID_TEST_DATA.value
            conf = 0.75
        else:
            classification = FailureCategory.APPLICATION_DEFECT.value
            conf = 0.70

        return {
            "test_id": test_id,
            "classification": classification,
            "confidence": conf,
            "conclusion": f"Observed failure '{failure_reason}' indicates possible {classification}.",
            "evidence": [f"Execution status: {exec_res.get('status')}", f"Failure detail: {failure_reason}"],
            "assumptions": ["Test executed in target staging/test environment."],
            "recommended_next_actions": ["Inspect service logs", "Verify request parameters and credentials"],
            "reasoning_summary": f"Deterministic failure analysis based on observed failure: {failure_reason}.",
        }
