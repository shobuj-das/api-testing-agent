"""OpenAPI 3 parser that produces validated, provider-neutral API models."""

from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from models.api_models import (
    APIEndpoint,
    APIParameter,
    APIResponseDefinition,
    APISpecification,
    HTTPMethod,
    ParameterLocation,
)

OPERATION_METHODS = frozenset(method.value.lower() for method in HTTPMethod)


class OpenAPIParseError(ValueError):
    """Raised when a supplied OpenAPI document cannot be safely parsed."""


class OpenAPIParser:
    """Parse OpenAPI 3.0/3.1 JSON or YAML without performing network requests."""

    def parse_file(self, spec_path: str | Path) -> APISpecification:
        """Load an OpenAPI JSON/YAML file and return normalized endpoint metadata."""
        path = Path(spec_path)
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise OpenAPIParseError(f"Unable to read specification '{path}': {exc}") from exc
        try:
            document = json.loads(content) if path.suffix.lower() == ".json" else yaml.safe_load(content)
        except (json.JSONDecodeError, yaml.YAMLError) as exc:
            raise OpenAPIParseError(f"Specification '{path}' contains invalid JSON/YAML: {exc}") from exc
        return self.parse_document(document)

    def parse_document(self, document: Any) -> APISpecification:
        """Validate and normalize an in-memory OpenAPI 3 document."""
        if not isinstance(document, Mapping):
            raise OpenAPIParseError("OpenAPI document must be an object.")
        version = document.get("openapi")
        if not isinstance(version, str) or not version.startswith("3."):
            raise OpenAPIParseError("Only OpenAPI 3.x documents are supported in this milestone.")
        info = document.get("info")
        if not isinstance(info, Mapping) or not isinstance(info.get("title"), str) or not isinstance(info.get("version"), str):
            raise OpenAPIParseError("OpenAPI document requires info.title and info.version strings.")
        paths = document.get("paths")
        if not isinstance(paths, Mapping):
            raise OpenAPIParseError("OpenAPI document requires a paths object.")

        endpoints: list[APIEndpoint] = []
        for path, path_item in paths.items():
            if not isinstance(path, str) or not isinstance(path_item, Mapping):
                raise OpenAPIParseError("Each paths entry must use a string path and object definition.")
            endpoints.extend(self._parse_path_item(document, path, path_item))
        servers = [item["url"] for item in document.get("servers", []) if isinstance(item, Mapping) and isinstance(item.get("url"), str)]
        return APISpecification(
            title=info["title"], version=info["version"], openapi_version=version,
            servers=servers, endpoints=endpoints,
        )

    def _parse_path_item(
        self, document: Mapping[str, Any], path: str, path_item: Mapping[str, Any]
    ) -> list[APIEndpoint]:
        shared_parameters = self._resolve_parameters(document, path_item.get("parameters", []))
        endpoints: list[APIEndpoint] = []
        for method, operation in path_item.items():
            if method.lower() not in OPERATION_METHODS or not isinstance(operation, Mapping):
                continue
            operation_parameters = self._resolve_parameters(document, operation.get("parameters", []))
            parameters = self._merge_parameters(shared_parameters, operation_parameters)
            request_schema, request_required = self._parse_request_body(document, operation.get("requestBody"))
            endpoints.append(APIEndpoint(
                method=HTTPMethod(method.upper()), path=path,
                summary=self._optional_string(operation.get("summary")),
                description=self._optional_string(operation.get("description")),
                operation_id=self._optional_string(operation.get("operationId")),
                parameters=parameters, request_body_schema=request_schema,
                request_body_required=bool(operation.get("requestBody", {}).get("required", False)) if isinstance(operation.get("requestBody"), Mapping) else request_required,
                responses=self._parse_responses(document, operation.get("responses", {})),
                authentication_required=self._requires_authentication(document, operation),
                tags=[tag for tag in operation.get("tags", []) if isinstance(tag, str)],
            ))
        return endpoints

    def _resolve_parameters(self, document: Mapping[str, Any], raw_parameters: Any) -> list[APIParameter]:
        if not isinstance(raw_parameters, list):
            raise OpenAPIParseError("parameters must be an array.")
        parsed: list[APIParameter] = []
        for item in raw_parameters:
            parameter = self._resolve_reference(document, item)
            if not isinstance(parameter, Mapping):
                raise OpenAPIParseError("Each parameter must be an object.")
            name, location = parameter.get("name"), parameter.get("in")
            if not isinstance(name, str) or location not in {location.value for location in ParameterLocation}:
                raise OpenAPIParseError("Parameters require valid name and in fields.")
            schema = self._resolve_reference(document, parameter.get("schema", {}))
            parsed.append(APIParameter(
                name=name, location=ParameterLocation(location),
                required=bool(parameter.get("required", False)),
                description=self._optional_string(parameter.get("description")),
                schema=schema if isinstance(schema, dict) else {},
            ))
        return parsed

    @staticmethod
    def _merge_parameters(shared: list[APIParameter], operation: list[APIParameter]) -> list[APIParameter]:
        merged = {(parameter.name, parameter.location): parameter for parameter in shared}
        merged.update({(parameter.name, parameter.location): parameter for parameter in operation})
        return list(merged.values())

    def _parse_request_body(self, document: Mapping[str, Any], raw_request_body: Any) -> tuple[dict[str, Any] | None, bool]:
        if raw_request_body is None:
            return None, False
        body = self._resolve_reference(document, raw_request_body)
        if not isinstance(body, Mapping):
            raise OpenAPIParseError("requestBody must be an object.")
        content = body.get("content", {})
        if not isinstance(content, Mapping):
            raise OpenAPIParseError("requestBody.content must be an object.")
        media = content.get("application/json") or next(iter(content.values()), None)
        if not isinstance(media, Mapping):
            return None, bool(body.get("required", False))
        schema = self._resolve_reference(document, media.get("schema", {}))
        return schema if isinstance(schema, dict) else None, bool(body.get("required", False))

    def _parse_responses(self, document: Mapping[str, Any], raw_responses: Any) -> list[APIResponseDefinition]:
        if not isinstance(raw_responses, Mapping):
            raise OpenAPIParseError("responses must be an object.")
        responses: list[APIResponseDefinition] = []
        for status_code, raw_response in raw_responses.items():
            response = self._resolve_reference(document, raw_response)
            if not isinstance(response, Mapping):
                raise OpenAPIParseError("Each response must be an object.")
            content = response.get("content", {})
            media_type, media = next(iter(content.items()), (None, None)) if isinstance(content, Mapping) else (None, None)
            schema = self._resolve_reference(document, media.get("schema", {})) if isinstance(media, Mapping) else None
            responses.append(APIResponseDefinition(
                status_code=str(status_code), description=self._optional_string(response.get("description")),
                content_type=media_type if isinstance(media_type, str) else None,
                schema=schema if isinstance(schema, dict) else None,
            ))
        return responses

    def _requires_authentication(self, document: Mapping[str, Any], operation: Mapping[str, Any]) -> bool:
        if "security" in operation:
            return bool(operation["security"])
        return bool(document.get("security"))

    def _resolve_reference(self, document: Mapping[str, Any], value: Any, seen: set[str] | None = None) -> Any:
        if not isinstance(value, Mapping) or "$ref" not in value:
            return deepcopy(value)
        reference = value["$ref"]
        if not isinstance(reference, str) or not reference.startswith("#/"):
            raise OpenAPIParseError("Only local OpenAPI $ref values are supported.")
        seen = seen or set()
        if reference in seen:
            raise OpenAPIParseError(f"Circular $ref detected: {reference}")
        target: Any = document
        for part in reference[2:].split("/"):
            if not isinstance(target, Mapping) or part not in target:
                raise OpenAPIParseError(f"Unresolvable $ref: {reference}")
            target = target[part]
        return self._resolve_reference(document, target, seen | {reference})

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        return value if isinstance(value, str) else None
