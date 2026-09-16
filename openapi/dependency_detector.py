"""Deterministic API dependency detection for resource lifecycle and authentication chains."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from models.api_models import APIEndpoint, APISpecification, HTTPMethod, ParameterLocation
from models.dependency import (
    APIDependency,
    ConsumedVariable,
    DependencyGraph,
    DependencyType,
    ProducedVariable,
    VariableSourceLocation,
)

AUTH_KEYWORDS = frozenset({"auth", "login", "token", "session", "oauth", "jwt"})
TOKEN_NAMES = frozenset({"token", "access_token", "auth_token", "jwt", "session_token", "session_id"})
ID_KEYWORDS = frozenset({"id", "uuid", "key", "number", "code"})


def _normalize_name(name: str) -> str:
    """Normalize variable names by stripping underscores and converting to lowercase."""
    return re.sub(r"[_\-\s]", "", name).lower()


def _extract_resource_name(path: str) -> str:
    """Extract primary resource name from a path, e.g. '/booking/{id}' -> 'booking'."""
    segments = [seg for seg in path.strip("/").split("/") if not (seg.startswith("{") and seg.endswith("}"))]
    return segments[0].lower() if segments else ""


class DependencyDetector:
    """Detect producer-consumer relationships between API operations deterministically."""

    def detect_dependencies(self, specification: APISpecification) -> DependencyGraph:
        """Analyze an entire API specification and return the resolved dependency graph."""
        produced_by_endpoint: dict[str, list[ProducedVariable]] = {}
        consumed_by_endpoint: dict[str, list[ConsumedVariable]] = {}

        for endpoint in specification.endpoints:
            endpoint_key = f"{endpoint.method.value} {endpoint.path}"
            produced_by_endpoint[endpoint_key] = self._detect_produced_variables(endpoint)
            consumed_by_endpoint[endpoint_key] = self._detect_consumed_variables(endpoint)

        dependencies: list[APIDependency] = []
        seen_deps: set[tuple[str, str, str, str]] = set()

        for prod_key, produced_vars in produced_by_endpoint.items():
            prod_method_str, prod_path = prod_key.split(" ", 1)
            prod_method = HTTPMethod(prod_method_str)

            for cons_key, consumed_vars in consumed_by_endpoint.items():
                cons_method_str, cons_path = cons_key.split(" ", 1)
                cons_method = HTTPMethod(cons_method_str)

                # An endpoint doesn't depend on itself for the same request
                if prod_key == cons_key:
                    continue

                for p_var in produced_vars:
                    for c_var in consumed_vars:
                        dep = self._evaluate_dependency(
                            prod_method, prod_path, p_var,
                            cons_method, cons_path, c_var,
                        )
                        if dep:
                            dep_sig = (
                                dep.producer_method.value,
                                dep.producer_path,
                                dep.consumer_method.value,
                                dep.consumer_path,
                            )
                            if dep_sig not in seen_deps:
                                seen_deps.add(dep_sig)
                                dependencies.append(dep)

        return DependencyGraph(
            dependencies=dependencies,
            produced_by_endpoint=produced_by_endpoint,
            consumed_by_endpoint=consumed_by_endpoint,
        )

    def _detect_produced_variables(self, endpoint: APIEndpoint) -> list[ProducedVariable]:
        """Find variables produced by success responses (200, 201, 202)."""
        produced: list[ProducedVariable] = []
        seen_names: set[str] = set()

        for response in endpoint.responses:
            if response.status_code not in {"200", "201", "202", "default"}:
                continue
            if not response.schema_definition or not isinstance(response.schema_definition, Mapping):
                continue

            self._traverse_schema_for_producers(
                response.schema_definition, prefix="", produced=produced, seen_names=seen_names
            )

        # Heuristic: If endpoint path contains auth/login and returns 200 with schema or unknown schema
        path_lower = endpoint.path.lower()
        if any(keyword in path_lower for keyword in AUTH_KEYWORDS) and "token" not in seen_names:
            produced.append(ProducedVariable(
                name="token",
                extraction_path="token",
                location=VariableSourceLocation.BODY,
                data_type="string",
                description=f"Authentication token produced by {endpoint.method.value} {endpoint.path}",
            ))
            seen_names.add("token")

        return produced

    def _traverse_schema_for_producers(
        self,
        schema: Mapping[str, Any],
        prefix: str,
        produced: list[ProducedVariable],
        seen_names: set[str],
        depth: int = 0,
    ) -> None:
        if depth > 3:
            return

        properties = schema.get("properties")
        if isinstance(properties, Mapping):
            for prop_name, prop_schema in properties.items():
                if not isinstance(prop_schema, Mapping):
                    continue
                full_path = f"{prefix}.{prop_name}" if prefix else prop_name
                prop_lower = prop_name.lower()
                data_type = str(prop_schema.get("type", "string"))
                # Check if it's an ID or Token (exclude booleans/unrelated words ending in id like paid, valid)
                NON_ID_WORDS = ("paid", "valid", "invalid", "grid", "fluid", "solid", "mid")
                is_id = (
                    data_type in {"integer", "string"}
                    and (
                        prop_lower == "id"
                        or prop_lower.endswith("_id")
                        or (prop_lower.endswith("id") and not any(prop_lower.endswith(w) for w in NON_ID_WORDS))
                        or any(prop_lower == k or prop_lower.endswith(f"_{k}") for k in ID_KEYWORDS)
                    )
                )
                is_token = any(keyword in prop_lower for keyword in TOKEN_NAMES)

                if (is_id or is_token) and prop_name not in seen_names:
                    produced.append(ProducedVariable(
                        name=prop_name,
                        extraction_path=full_path,
                        location=VariableSourceLocation.BODY,
                        data_type=data_type,
                        description=prop_schema.get("description"),
                    ))
                    seen_names.add(prop_name)

                if prop_schema.get("type") == "object":
                    self._traverse_schema_for_producers(
                        prop_schema, full_path, produced, seen_names, depth + 1
                    )

    def _detect_consumed_variables(self, endpoint: APIEndpoint) -> list[ConsumedVariable]:
        """Find variables consumed as path, query, header parameters, or auth."""
        consumed: list[ConsumedVariable] = []
        seen_params: set[str] = set()

        for param in endpoint.parameters:
            consumed.append(ConsumedVariable(
                name=param.name,
                parameter_name=param.name,
                location=param.location,
                required=param.required,
                description=param.description,
            ))
            seen_params.add(param.name.lower())

        # If endpoint requires authentication, record that it consumes an auth token
        if endpoint.authentication_required and "authorization" not in seen_params and "token" not in seen_params:
            consumed.append(ConsumedVariable(
                name="auth_token",
                parameter_name="Authorization",
                location=ParameterLocation.HEADER,
                required=True,
                description=f"Authentication token required for {endpoint.method.value} {endpoint.path}",
            ))

        return consumed

    def _evaluate_dependency(
        self,
        prod_method: HTTPMethod,
        prod_path: str,
        prod_var: ProducedVariable,
        cons_method: HTTPMethod,
        cons_path: str,
        cons_var: ConsumedVariable,
    ) -> APIDependency | None:
        """Evaluate whether a produced variable fulfills a consumed variable requirement."""
        p_name_norm = _normalize_name(prod_var.name)
        c_name_norm = _normalize_name(cons_var.name)
        prod_resource = _extract_resource_name(prod_path)
        cons_resource = _extract_resource_name(cons_path)

        # 1. Authentication dependency
        is_prod_token = (
            any(k in p_name_norm for k in TOKEN_NAMES)
            or any(k in prod_path.lower() for k in AUTH_KEYWORDS)
        )
        is_cons_auth = (
            cons_var.location is ParameterLocation.HEADER
            and (
                "auth" in c_name_norm
                or "token" in c_name_norm
                or cons_var.parameter_name.lower() in {"authorization", "cookie", "x-auth-token"}
            )
        ) or any(k in c_name_norm for k in TOKEN_NAMES)

        if is_prod_token and is_cons_auth:
            evidence = [
                f"{prod_method.value} {prod_path} produces authentication token '{prod_var.name}' in response",
                f"{cons_method.value} {cons_path} consumes '{cons_var.parameter_name}' ({cons_var.location.value})",
            ]
            return APIDependency(
                producer_method=prod_method,
                producer_path=prod_path,
                consumer_method=cons_method,
                consumer_path=cons_path,
                dependency_type=DependencyType.AUTHENTICATION,
                variable_name=prod_var.name,
                extraction_path=prod_var.extraction_path,
                target_parameter=cons_var.parameter_name,
                target_location=cons_var.location,
                confidence=0.95,
                evidence=evidence,
                is_deterministic=True,
            )

        # 2. Resource lifecycle dependency (e.g. POST /booking -> GET/PUT/DELETE /booking/{id})
        is_same_resource = prod_resource and cons_resource and (prod_resource == cons_resource)

        # Name match conditions:
        # - Exact / normalized match: e.g. booking_id == bookingid
        name_match = (p_name_norm == c_name_norm) or (p_name_norm in c_name_norm) or (c_name_norm in p_name_norm)

        # - Generic ID match when resources match:
        # e.g. POST /booking returns 'bookingid', GET /booking/{id} consumes 'id'
        # or POST /booking returns 'id', GET /booking/{booking_id} consumes 'booking_id'
        generic_id_match = (
            is_same_resource
            and (p_name_norm in ID_KEYWORDS or any(p_name_norm.endswith(k) for k in ID_KEYWORDS))
            and (c_name_norm in ID_KEYWORDS or any(c_name_norm.endswith(k) for k in ID_KEYWORDS))
        )

        if (name_match or generic_id_match) and cons_var.location is ParameterLocation.PATH:
            dep_type = DependencyType.RESOURCE_LIFECYCLE if is_same_resource else DependencyType.ASSOCIATION
            confidence = 0.95 if (is_same_resource and prod_method is HTTPMethod.POST) else 0.85
            evidence = [
                f"{prod_method.value} {prod_path} produces '{prod_var.name}' via '{prod_var.extraction_path}'",
                f"{cons_method.value} {cons_path} consumes path parameter '{cons_var.parameter_name}'",
            ]
            if is_same_resource:
                evidence.append(f"Operations share common resource '{prod_resource}'")

            return APIDependency(
                producer_method=prod_method,
                producer_path=prod_path,
                consumer_method=cons_method,
                consumer_path=cons_path,
                dependency_type=dep_type,
                variable_name=prod_var.name,
                extraction_path=prod_var.extraction_path,
                target_parameter=cons_var.parameter_name,
                target_location=cons_var.location,
                confidence=confidence,
                evidence=evidence,
                is_deterministic=True,
            )

        # 3. Association match for query/body parameters
        if is_same_resource and name_match and cons_var.location in {ParameterLocation.QUERY, ParameterLocation.HEADER}:
            evidence = [
                f"{prod_method.value} {prod_path} produces '{prod_var.name}'",
                f"{cons_method.value} {cons_path} consumes '{cons_var.parameter_name}' ({cons_var.location.value})",
            ]
            return APIDependency(
                producer_method=prod_method,
                producer_path=prod_path,
                consumer_method=cons_method,
                consumer_path=cons_path,
                dependency_type=DependencyType.ASSOCIATION,
                variable_name=prod_var.name,
                extraction_path=prod_var.extraction_path,
                target_parameter=cons_var.parameter_name,
                target_location=cons_var.location,
                confidence=0.75,
                evidence=evidence,
                is_deterministic=True,
            )

        return None
