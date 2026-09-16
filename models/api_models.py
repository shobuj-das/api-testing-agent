"""Strict, provider-neutral representations of an API specification."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HTTPMethod(StrEnum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class ParameterLocation(StrEnum):
    PATH = "path"
    QUERY = "query"
    HEADER = "header"
    COOKIE = "cookie"


class SchemaField(BaseModel):
    """A normalized schema property, retained without losing OpenAPI constraints."""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    name: str = Field(min_length=1)
    data_type: str = Field(min_length=1)
    required: bool = False
    description: str | None = None
    enum: list[Any] | None = None
    constraints: dict[str, Any] = Field(default_factory=dict)


class APIParameter(BaseModel):
    """An input parameter extracted from an API specification."""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    name: str = Field(min_length=1)
    location: ParameterLocation
    required: bool = False
    description: str | None = None
    schema_definition: dict[str, Any] = Field(
        default_factory=dict, validation_alias="schema", serialization_alias="schema"
    )

    @field_validator("required")
    @classmethod
    def path_parameters_are_required(cls, required: bool, info: Any) -> bool:
        if info.data.get("location") is ParameterLocation.PATH and not required:
            raise ValueError("Path parameters must be required by OpenAPI.")
        return required


class APIResponseDefinition(BaseModel):
    """A documented response associated with an endpoint."""

    model_config = ConfigDict(extra="forbid", strict=True)

    status_code: str = Field(min_length=1)
    description: str | None = None
    content_type: str | None = None
    schema_definition: dict[str, Any] | None = Field(
        default=None, validation_alias="schema", serialization_alias="schema"
    )


class APIEndpoint(BaseModel):
    """Normalized operation metadata produced by the OpenAPI parser."""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    method: HTTPMethod
    path: str = Field(min_length=1)
    summary: str | None = None
    description: str | None = None
    operation_id: str | None = None
    parameters: list[APIParameter] = Field(default_factory=list)
    request_body_schema: dict[str, Any] | None = None
    request_body_required: bool = False
    responses: list[APIResponseDefinition] = Field(default_factory=list)
    authentication_required: bool = False
    tags: list[str] = Field(default_factory=list)

    @field_validator("path")
    @classmethod
    def path_must_be_relative(cls, path: str) -> str:
        if not path.startswith("/") or "://" in path:
            raise ValueError("Endpoint path must be a relative path beginning with '/'.")
        return path


class APISpecification(BaseModel):
    """Normalized OpenAPI document used by subsequent planning stages."""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    title: str = Field(min_length=1)
    version: str = Field(min_length=1)
    openapi_version: str = Field(min_length=1)
    servers: list[str] = Field(default_factory=list)
    endpoints: list[APIEndpoint] = Field(default_factory=list)
