"""Bounded coordinator for API understanding, generation, execution and analysis."""

from __future__ import annotations

from collections.abc import Mapping

from agents.api_understanding_agent import APIUnderstandingAgent
from agents.failure_analysis_agent import FailureAnalysisAgent
from agents.test_generation_agent import TestGenerationAgent
from agents.workflow_builder import WorkflowBuilder
from executor.api_executor import APIExecutor
from executor.workflow_executor import WorkflowExecutor
from models.agent_state import AgentAction, AgentDecision, AgentState
from models.api_models import APISpecification
from models.execution_models import ExecutionStatus
from models.failure_analysis import FailureCategory
from models.test_case import TestCase
from models.test_plan import TestPlan
from models.workflow import Workflow
from openapi.dependency_detector import DependencyDetector


class OrchestratorError(RuntimeError):
    """Raised when coordination input violates a deterministic safety invariant."""


class AgentOrchestrator:
    """Run an explicitly bounded agent loop; no decision may trigger arbitrary code."""

    def __init__(
        self,
        understanding_agent: APIUnderstandingAgent,
        generation_agent: TestGenerationAgent,
        executor: APIExecutor,
        failure_agent: FailureAnalysisAgent,
        *,
        max_iterations: int = 25,
        max_retries: int = 1,
        max_generated_tests: int = 50,
        workflow_executor: WorkflowExecutor | None = None,
        dependency_detector: DependencyDetector | None = None,
        workflow_builder: WorkflowBuilder | None = None,
        enable_workflows: bool | None = None,
    ) -> None:
        if max_iterations <= 0 or max_generated_tests <= 0 or max_retries < 0:
            raise ValueError("Iterations/tests must be positive; retries cannot be negative.")
        self._understanding_agent = understanding_agent
        self._generation_agent = generation_agent
        self._executor = executor
        self._failure_agent = failure_agent
        self._max_iterations = max_iterations
        self._max_retries = max_retries
        self._max_generated_tests = max_generated_tests

        self._enable_workflows = (
            enable_workflows if enable_workflows is not None else (workflow_executor is not None)
        )
        self._workflow_executor = workflow_executor or (
            WorkflowExecutor(executor) if self._enable_workflows else None
        )
        self._dependency_detector = dependency_detector or (
            DependencyDetector() if self._enable_workflows else None
        )
        self._workflow_builder = workflow_builder or (
            WorkflowBuilder() if self._enable_workflows else None
        )

    def run(
        self, specification: APISpecification, *, variables: Mapping[str, object] | None = None
    ) -> AgentState:
        """Run until testing work is complete or a configured limit is reached."""
        state = AgentState(
            api_information=specification,
            remaining_tasks=[endpoint.path for endpoint in specification.endpoints],
        )
        state.endpoint_understandings = self._understanding_agent.understand_specification(specification)
        if len(state.endpoint_understandings) != len(specification.endpoints):
            raise OrchestratorError("Understanding agent did not return one record per endpoint.")

        while state.iteration < self._max_iterations:
            if state.current_action is AgentAction.STOP:
                self._record_decision(state, AgentAction.STOP, "Testing objective is complete or bounded.")
                break
            state.iteration += 1
            self._step(state, variables or {})
        else:
            state.current_action = AgentAction.STOP
            self._record_decision(
                state, AgentAction.STOP,
                "Maximum agent iterations reached; remaining work was stopped safely.",
                [f"max_iterations={self._max_iterations}"],
            )
        return state

    def _step(self, state: AgentState, variables: Mapping[str, object]) -> None:
        if state.current_action is AgentAction.GENERATE_TEST:
            self._generate_next_endpoint(state)
        elif state.current_action in {AgentAction.EXECUTE_TEST, AgentAction.RETRY_TEST}:
            self._execute_next_test(state, variables)
        elif state.current_action is AgentAction.ANALYZE_FAILURE:
            self._analyze_pending_failure(state)
        elif state.current_action is AgentAction.BUILD_WORKFLOW:
            self._build_workflows(state)
        elif state.current_action is AgentAction.EXECUTE_WORKFLOW:
            self._execute_next_workflow(state, variables)
        else:
            raise OrchestratorError(f"Action {state.current_action} is not handled by the orchestrator.")

    def _generate_next_endpoint(self, state: AgentState) -> None:
        endpoint_index = state.next_endpoint_index
        if endpoint_index >= len(state.api_information.endpoints) or len(state.generated_tests) >= self._max_generated_tests:
            self._refresh_plan(state)
            if state.pending_test_ids:
                state.current_action = AgentAction.EXECUTE_TEST
            elif self._enable_workflows and not state.workflows_built:
                state.current_action = AgentAction.BUILD_WORKFLOW
            else:
                state.current_action = AgentAction.STOP

            self._record_decision(
                state, state.current_action,
                "Generation is complete; moving to execution or workflows.",
                [f"generated_tests={len(state.generated_tests)}"],
            )
            return
        endpoint = state.api_information.endpoints[endpoint_index]
        understanding = state.endpoint_understandings[endpoint_index]
        remaining_capacity = self._max_generated_tests - len(state.generated_tests)
        result = self._generation_agent.generate_for_endpoint(
            endpoint, understanding, max_tests=remaining_capacity,
        )
        known_ids = {test_case.id for test_case in state.generated_tests}
        for test_case in result.test_cases:
            if test_case.id in known_ids:
                raise OrchestratorError(f"Generated test ID collides with an existing test: {test_case.id}")
            known_ids.add(test_case.id)
            state.generated_tests.append(test_case)
            state.pending_test_ids.append(test_case.id)
        state.remaining_tasks = state.remaining_tasks[1:]
        state.next_endpoint_index += 1
        self._record_decision(
            state, AgentAction.GENERATE_TEST,
            result.reasoning_summary,
            [*result.evidence, f"duplicates_removed={result.duplicates_removed}"],
        )
        state.current_action = AgentAction.GENERATE_TEST

    def _execute_next_test(self, state: AgentState, variables: Mapping[str, object]) -> None:
        if not state.pending_test_ids:
            if self._enable_workflows and not state.workflows_built:
                state.current_action = AgentAction.BUILD_WORKFLOW
            else:
                state.current_action = AgentAction.STOP
            return
        test_id = state.pending_test_ids.pop(0)
        test_case = self._test_by_id(state.generated_tests, test_id)
        action = state.current_action
        result = self._executor.execute(test_case, variables=variables)
        state.execution_results.append(result)
        self._record_decision(
            state, action, f"Executed test '{test_id}' with status {result.status}.",
            [result.failure_reason] if result.failure_reason else [],
        )
        if result.status in {ExecutionStatus.FAILED, ExecutionStatus.ERROR}:
            state.pending_failure_test_id = test_id
            state.current_action = AgentAction.ANALYZE_FAILURE
        else:
            if state.pending_test_ids:
                state.current_action = AgentAction.EXECUTE_TEST
            elif self._enable_workflows and not state.workflows_built:
                state.current_action = AgentAction.BUILD_WORKFLOW
            else:
                state.current_action = AgentAction.STOP

    def _analyze_pending_failure(self, state: AgentState) -> None:
        test_id = state.pending_failure_test_id
        if not test_id or not state.execution_results:
            raise OrchestratorError("Failure analysis has no pending failed execution.")
        test_case = self._test_by_id(state.generated_tests, test_id)
        result = state.execution_results[-1]
        analysis = self._failure_agent.analyze_failure(test_case, result)
        state.failures.append(analysis)
        retry_count = state.retry_counts.get(test_id, 0)
        if self._should_retry(result.status, analysis.classification) and retry_count < self._max_retries:
            state.retry_counts[test_id] = retry_count + 1
            state.pending_test_ids.insert(0, test_id)
            state.current_action = AgentAction.RETRY_TEST
            next_action = AgentAction.RETRY_TEST
            summary = f"Failure analysis recommends a bounded retry for '{test_id}'."
        else:
            if state.pending_test_ids:
                next_action = AgentAction.EXECUTE_TEST
            elif self._enable_workflows and not state.workflows_built:
                next_action = AgentAction.BUILD_WORKFLOW
            else:
                next_action = AgentAction.STOP
            state.current_action = next_action
            summary = f"Failure analysis completed for '{test_id}'; continuing without retry."
        state.pending_failure_test_id = None
        self._record_decision(
            state, next_action, summary,
            [*analysis.evidence, f"classification={analysis.classification}", f"confidence={analysis.confidence}"],
        )

    def _build_workflows(self, state: AgentState) -> None:
        """Synthesize workflows based on dependencies detected from the API specification."""
        assert self._dependency_detector is not None
        assert self._workflow_builder is not None
        graph = self._dependency_detector.detect_dependencies(state.api_information)
        built_workflows = self._workflow_builder.build_lifecycle_workflows(state.api_information, graph)
        state.workflows = [wf.model_dump(mode="json") for wf in built_workflows]
        state.workflows_built = True

        if built_workflows:
            state.current_action = AgentAction.EXECUTE_WORKFLOW
            self._record_decision(
                state, AgentAction.BUILD_WORKFLOW,
                f"Built {len(built_workflows)} lifecycle workflow(s) based on detected dependencies.",
                [f"workflow_count={len(built_workflows)}", f"dependencies_found={len(graph.dependencies)}"],
            )
        else:
            state.current_action = AgentAction.STOP
            self._record_decision(
                state, AgentAction.BUILD_WORKFLOW,
                "No lifecycle workflows were identified from API dependencies; stopping.",
                [],
            )

    def _execute_next_workflow(self, state: AgentState, variables: Mapping[str, object]) -> None:
        """Execute the next pending workflow."""
        if state.pending_workflow_index >= len(state.workflows):
            state.current_action = AgentAction.STOP
            return

        assert self._workflow_executor is not None
        raw_wf = state.workflows[state.pending_workflow_index]
        import json
        workflow = Workflow.model_validate_json(json.dumps(raw_wf)) if isinstance(raw_wf, dict) else raw_wf
        state.pending_workflow_index += 1

        result = self._workflow_executor.execute(workflow, variables=variables)
        state.workflow_results.append(result.model_dump(mode="json"))

        status_str = "passed" if result.passed else "failed"
        self._record_decision(
            state, AgentAction.EXECUTE_WORKFLOW,
            f"Executed workflow '{workflow.name}' with outcome: {status_str}.",
            [result.failure_reason] if result.failure_reason else [f"steps_executed={len(result.step_results)}"],
        )

        if state.pending_workflow_index < len(state.workflows):
            state.current_action = AgentAction.EXECUTE_WORKFLOW
        else:
            state.current_action = AgentAction.STOP

    @staticmethod
    def _should_retry(status: ExecutionStatus, classification: FailureCategory) -> bool:
        return status is ExecutionStatus.ERROR or classification in {
            FailureCategory.TIMEOUT,
            FailureCategory.INTERMITTENT_FAILURE,
            FailureCategory.ENVIRONMENT_ISSUE,
            FailureCategory.DEPENDENCY_ISSUE,
        }

    @staticmethod
    def _test_by_id(test_cases: list[TestCase], test_id: str) -> TestCase:
        for test_case in test_cases:
            if test_case.id == test_id:
                return test_case
        raise OrchestratorError(f"Pending test '{test_id}' was not found in generated tests.")

    @staticmethod
    def _refresh_plan(state: AgentState) -> None:
        state.test_plan = TestPlan(
            name=f"{state.api_information.title} generated test plan",
            objective=f"Validate {state.api_information.title} endpoints.",
            test_cases=state.generated_tests,
            reasoning_summary="Generated by the bounded API testing agent.",
            source="agent",
        )

    @staticmethod
    def _record_decision(
        state: AgentState, action: AgentAction, summary: str, evidence: list[str] | None = None
    ) -> None:
        state.decisions.append(AgentDecision(
            iteration=state.iteration, action=action, reasoning_summary=summary,
            evidence=[item for item in (evidence or []) if item],
        ))
