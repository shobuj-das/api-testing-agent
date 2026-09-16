"""Automatic synthesis of executable workflows from OpenAPI specs and detected dependencies."""

from __future__ import annotations

import re
from typing import Any

from models.api_models import APIEndpoint, APISpecification, HTTPMethod, ParameterLocation
from models.dependency import APIDependency, DependencyGraph, DependencyType, VariableSourceLocation
from models.test_case import Assertion, AssertionType, Priority, TestCategory, TestCase
from models.workflow import VariableExtractionRule, Workflow, WorkflowStep


class WorkflowBuilder:
    """Build executable multi-step workflows from OpenAPI specifications and dependency graphs."""

    def build_lifecycle_workflows(
        self,
        specification: APISpecification,
        dependency_graph: DependencyGraph,
        *,
        default_payloads: dict[str, Any] | None = None,
    ) -> list[Workflow]:
        """Automatically synthesize end-to-end CRUD and auth workflows."""
        workflows: list[Workflow] = []
        payloads = default_payloads or {}

        # 1. Look for auth endpoint
        auth_dep = next(
            (d for d in dependency_graph.dependencies if d.dependency_type == DependencyType.AUTHENTICATION),
            None,
        )

        # 2. Group lifecycle dependencies by resource
        lifecycle_deps = [
            d for d in dependency_graph.dependencies
            if d.dependency_type == DependencyType.RESOURCE_LIFECYCLE
        ]

        # Group by producer endpoint
        producers = {dep.producer_path: dep for dep in lifecycle_deps}

        for prod_path, dep in producers.items():
            # Find the producer endpoint in specification
            prod_ep = next(
                (ep for ep in specification.endpoints if ep.path == prod_path and ep.method == dep.producer_method),
                None,
            )
            if not prod_ep:
                continue

            resource_name = dep.extraction_path.replace("id", "").strip("_") or "resource"
            workflow_id = f"workflow-{resource_name}-lifecycle"
            steps: list[WorkflowStep] = []

            # Step 1: Optional Auth step if required
            auth_step_added = False
            if auth_dep and (prod_ep.authentication_required or any(
                ep.authentication_required
                for ep in specification.endpoints
                if ep.path.startswith(prod_path)
            )):
                auth_ep = next(
                    (ep for ep in specification.endpoints if ep.path == auth_dep.producer_path and ep.method == auth_dep.producer_method),
                    None,
                )
                if auth_ep:
                    auth_body = payloads.get(
                        auth_ep.path,
                        {"username": "admin", "password": "password123"},
                    )
                    auth_step = WorkflowStep(
                        step_id=f"{workflow_id}-auth",
                        name=f"Authenticate via {auth_ep.method.value} {auth_ep.path}",
                        description="Authenticate and extract auth token for subsequent requests.",
                        test_case=TestCase(
                            id=f"{workflow_id}-auth-tc",
                            title=f"Authenticate {auth_ep.path}",
                            description="Obtain session auth token",
                            method=auth_ep.method,
                            endpoint=auth_ep.path,
                            request_body=auth_body,
                            expected_status=200,
                            category=TestCategory.WORKFLOW,
                            priority=Priority.CRITICAL,
                            source="workflow_builder",
                        ),
                        extract_variables=[
                            VariableExtractionRule(
                                source=VariableSourceLocation.BODY,
                                field_path=auth_dep.extraction_path,
                                variable_name=auth_dep.variable_name,
                            )
                        ],
                    )
                    steps.append(auth_step)
                    auth_step_added = True

            # Step 2: Create resource (POST)
            create_body = payloads.get(
                prod_ep.path,
                self._generate_sample_body(prod_ep),
            )
            create_step = WorkflowStep(
                step_id=f"{workflow_id}-create",
                name=f"Create {resource_name}",
                description=f"Create a new {resource_name} and extract its ID.",
                test_case=TestCase(
                    id=f"{workflow_id}-create-tc",
                    title=f"Create {resource_name}",
                    description=f"Issue POST to {prod_ep.path}",
                    method=prod_ep.method,
                    endpoint=prod_ep.path,
                    request_body=create_body,
                    expected_status=200,
                    category=TestCategory.WORKFLOW,
                    priority=Priority.CRITICAL,
                    source="workflow_builder",
                ),
                extract_variables=[
                    VariableExtractionRule(
                        source=VariableSourceLocation.BODY,
                        field_path=dep.extraction_path,
                        variable_name=dep.target_parameter,
                    )
                ],
            )
            steps.append(create_step)

            # Step 3: GET resource by ID
            target_var_pattern = f"{{{{{dep.target_parameter}}}}}"
            var_path = re.sub(r"\{[a-zA-Z0-9_]+\}", target_var_pattern, dep.consumer_path)

            get_ep = next(
                (ep for ep in specification.endpoints if ep.path == dep.consumer_path and ep.method == HTTPMethod.GET),
                None,
            )
            if get_ep:
                steps.append(
                    WorkflowStep(
                        step_id=f"{workflow_id}-get",
                        name=f"Retrieve created {resource_name}",
                        description=f"Verify {resource_name} can be retrieved using dynamic ID.",
                        test_case=TestCase(
                            id=f"{workflow_id}-get-tc",
                            title=f"Get {resource_name}",
                            description=f"Retrieve {resource_name} via {var_path}",
                            method=HTTPMethod.GET,
                            endpoint=var_path,
                            expected_status=200,
                            category=TestCategory.WORKFLOW,
                            priority=Priority.HIGH,
                            source="workflow_builder",
                        ),
                    )
                )

            # Step 4: PUT/PATCH update resource
            update_ep = next(
                (ep for ep in specification.endpoints if ep.path == dep.consumer_path and ep.method in {HTTPMethod.PUT, HTTPMethod.PATCH}),
                None,
            )
            if update_ep:
                headers = {}
                if auth_step_added and auth_dep:
                    headers["Cookie"] = f"token={{{{{auth_dep.variable_name}}}}}"
                    headers["Authorization"] = f"Bearer {{{{{auth_dep.variable_name}}}}}"

                steps.append(
                    WorkflowStep(
                        step_id=f"{workflow_id}-update",
                        name=f"Update {resource_name}",
                        description=f"Update {resource_name} via {update_ep.method.value}.",
                        test_case=TestCase(
                            id=f"{workflow_id}-update-tc",
                            title=f"Update {resource_name}",
                            description=f"Update {resource_name} details",
                            method=update_ep.method,
                            endpoint=var_path,
                            headers=headers,
                            request_body=create_body,
                            expected_status=200,
                            category=TestCategory.WORKFLOW,
                            priority=Priority.HIGH,
                            source="workflow_builder",
                        ),
                    )
                )

            # Step 5: DELETE resource (Cleanup)
            delete_ep = next(
                (ep for ep in specification.endpoints if ep.path == dep.consumer_path and ep.method == HTTPMethod.DELETE),
                None,
            )
            if delete_ep:
                del_headers = {}
                if auth_step_added and auth_dep:
                    del_headers["Cookie"] = f"token={{{{{auth_dep.variable_name}}}}}"
                    del_headers["Authorization"] = f"Bearer {{{{{auth_dep.variable_name}}}}}"

                steps.append(
                    WorkflowStep(
                        step_id=f"{workflow_id}-delete",
                        name=f"Delete and cleanup {resource_name}",
                        description=f"Delete {resource_name} to ensure clean environment.",
                        test_case=TestCase(
                            id=f"{workflow_id}-delete-tc",
                            title=f"Delete {resource_name}",
                            description=f"Delete {resource_name} via DELETE {var_path}",
                            method=HTTPMethod.DELETE,
                            endpoint=var_path,
                            headers=del_headers,
                            expected_status=201,  # Restful booker returns 201 Created for DELETE
                            assertions=[
                                Assertion(
                                    assertion_type=AssertionType.STATUS_CODE_IN,
                                    expected=[200, 201, 204],
                                    description="Delete status code can be 200, 201, or 204",
                                )
                            ],
                            category=TestCategory.WORKFLOW,
                            priority=Priority.HIGH,
                            source="workflow_builder",
                        ),
                        is_cleanup=True,
                    )
                )

            workflows.append(
                Workflow(
                    id=workflow_id,
                    name=f"{resource_name.capitalize()} Lifecycle Workflow",
                    description=f"End-to-end CRUD workflow for {resource_name}.",
                    steps=steps,
                )
            )

        return workflows

    @staticmethod
    def _generate_sample_body(endpoint: APIEndpoint) -> dict[str, Any]:
        """Generate a basic sample body based on schema if available."""
        if not endpoint.request_body_schema:
            return {}
        properties = endpoint.request_body_schema.get("properties", {})
        sample: dict[str, Any] = {}
        for prop, details in properties.items():
            if isinstance(details, dict):
                prop_type = details.get("type", "string")
                if prop_type == "string":
                    sample[prop] = f"sample_{prop}"
                elif prop_type == "integer":
                    sample[prop] = 100
                elif prop_type == "boolean":
                    sample[prop] = True
                elif prop_type == "object":
                    sample[prop] = {}
                else:
                    sample[prop] = None
        return sample
