"""Models for representing API operation dependencies, produced variables, and consumed variables."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from models.api_models import HTTPMethod, ParameterLocation


class VariableSourceLocation(StrEnum):
    BODY = "body"
    HEADER = "header"
    PATH = "path"
    QUERY = "query"


class DependencyType(StrEnum):
    AUTHENTICATION = "authentication"
    RESOURCE_LIFECYCLE = "resource_lifecycle"
    ASSOCIATION = "association"


class ProducedVariable(BaseModel):
    """A variable produced by an API operation (e.g. an ID or auth token in a response)."""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    name: str = Field(min_length=1)
    extraction_path: str = Field(min_length=1)
    location: VariableSourceLocation = VariableSourceLocation.BODY
    data_type: str = Field(default="string", min_length=1)
    description: str | None = None


class ConsumedVariable(BaseModel):
    """A variable consumed by an API operation (e.g. a path parameter or auth header)."""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    name: str = Field(min_length=1)
    parameter_name: str = Field(min_length=1)
    location: ParameterLocation
    required: bool = False
    description: str | None = None


class APIDependency(BaseModel):
    """A detected explainable relationship between a producer and consumer operation."""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    producer_method: HTTPMethod
    producer_path: str = Field(min_length=1)
    consumer_method: HTTPMethod
    consumer_path: str = Field(min_length=1)
    dependency_type: DependencyType
    variable_name: str = Field(min_length=1)
    extraction_path: str = Field(min_length=1)
    target_parameter: str = Field(min_length=1)
    target_location: ParameterLocation
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(min_length=1)
    is_deterministic: bool = True

    @field_validator("producer_path", "consumer_path")
    @classmethod
    def path_must_be_relative(cls, path: str) -> str:
        if not path.startswith("/") or "://" in path:
            raise ValueError("Endpoint path must be a relative path beginning with '/'.")
        return path


class DependencyGraph(BaseModel):
    """A collection of detected dependencies across an entire API specification."""

    model_config = ConfigDict(extra="forbid", strict=True)

    dependencies: list[APIDependency] = Field(default_factory=list)
    produced_by_endpoint: dict[str, list[ProducedVariable]] = Field(default_factory=dict)
    consumed_by_endpoint: dict[str, list[ConsumedVariable]] = Field(default_factory=dict)
