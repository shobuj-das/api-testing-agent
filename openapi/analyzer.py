"""Deterministic endpoint observations for use by the later AI understanding agent."""

from __future__ import annotations

from dataclasses import dataclass

from models.api_models import APIEndpoint, APISpecification, ParameterLocation


@dataclass(frozen=True, slots=True)
class EndpointAnalysis:
    """Explainable, non-AI facts derived directly from an endpoint definition."""

    method: str
    path: str
    required_inputs: tuple[str, ...]
    optional_inputs: tuple[str, ...]
    documented_status_codes: tuple[str, ...]
    authentication_required: bool
    has_request_body: bool


class OpenAPIAnalyzer:
    """Extract deterministic observations, leaving inference to the AI layer."""

    def analyze_endpoint(self, endpoint: APIEndpoint) -> EndpointAnalysis:
        required_inputs = []
        optional_inputs = []
        for parameter in endpoint.parameters:
            label = f"{parameter.location}:{parameter.name}"
            (required_inputs if parameter.required else optional_inputs).append(label)
        if endpoint.request_body_schema:
            required = endpoint.request_body_schema.get("required", [])
            properties = endpoint.request_body_schema.get("properties", {})
            if isinstance(required, list) and isinstance(properties, dict):
                required_inputs.extend(f"body:{name}" for name in required if isinstance(name, str))
                optional_inputs.extend(
                    f"body:{name}" for name in properties
                    if isinstance(name, str) and name not in required
                )
        return EndpointAnalysis(
            method=endpoint.method.value, path=endpoint.path,
            required_inputs=tuple(required_inputs), optional_inputs=tuple(optional_inputs),
            documented_status_codes=tuple(response.status_code for response in endpoint.responses),
            authentication_required=endpoint.authentication_required,
            has_request_body=endpoint.request_body_schema is not None,
        )

    def analyze_specification(self, specification: APISpecification) -> list[EndpointAnalysis]:
        return [self.analyze_endpoint(endpoint) for endpoint in specification.endpoints]
