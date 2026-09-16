"""Structured API understanding agent built on parsed specification facts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from ai.llm_client import LLMClient
from models.api_models import APIEndpoint, APISpecification
from models.api_understanding import EndpointUnderstanding
from openapi.analyzer import OpenAPIAnalyzer


class UnderstandingError(ValueError):
    """Raised when an AI understanding result does not match its source endpoint."""


class APIUnderstandingAgent:
    """Generate validated API-understanding records from an OpenAPI endpoint."""

    def __init__(self, llm_client: LLMClient, analyzer: OpenAPIAnalyzer | None = None) -> None:
        self._llm_client = llm_client
        self._analyzer = analyzer or OpenAPIAnalyzer()
        self._cache: dict[str, EndpointUnderstanding] = {}

    def understand_endpoint(
        self, endpoint: APIEndpoint, *, force_refresh: bool = False
    ) -> EndpointUnderstanding:
        """Produce one validated understanding; identical endpoint metadata is cached."""
        cache_key = self._endpoint_cache_key(endpoint)
        if not force_refresh and cache_key in self._cache:
            return self._cache[cache_key]

        deterministic_facts = asdict(self._analyzer.analyze_endpoint(endpoint))
        task = (
            "Analyze this OpenAPI endpoint for API testing. Preserve evidence boundaries: "
            "documented facts must cite the supplied endpoint or deterministic facts; label any "
            "dependency as a hint and avoid claiming certainty without evidence. Include concise "
            "negative and boundary scenarios that are supported by the specification.\n\n"
            f"Endpoint metadata:\n{json.dumps(endpoint.model_dump(by_alias=True), sort_keys=True)}\n\n"
            f"Deterministic facts:\n{json.dumps(deterministic_facts, sort_keys=True)}"
        )
        understanding = self._llm_client.generate_structured(task, EndpointUnderstanding)
        if understanding.method.upper() != endpoint.method.value or understanding.path != endpoint.path:
            raise UnderstandingError(
                "AI understanding identity does not match the endpoint it was asked to analyze."
            )
        if understanding.authentication_required != endpoint.authentication_required:
            raise UnderstandingError(
                "AI understanding authentication requirement does not match the OpenAPI endpoint."
            )
        declared_required_inputs = {
            f"{input_item.location}:{input_item.name}"
            for input_item in understanding.required_inputs
        }
        expected_required_inputs = set(deterministic_facts["required_inputs"])
        missing_inputs = expected_required_inputs - declared_required_inputs
        if missing_inputs:
            raise UnderstandingError(
                "AI understanding omits required OpenAPI inputs: "
                f"{', '.join(sorted(missing_inputs))}."
            )
        self._cache[cache_key] = understanding
        return understanding

    def understand_specification(self, specification: APISpecification) -> list[EndpointUnderstanding]:
        """Understand every endpoint in source-document order."""
        return [self.understand_endpoint(endpoint) for endpoint in specification.endpoints]

    @staticmethod
    def _endpoint_cache_key(endpoint: APIEndpoint) -> str:
        serialized = json.dumps(endpoint.model_dump(by_alias=True), sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
