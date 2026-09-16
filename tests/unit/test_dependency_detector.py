"""Unit tests for Milestone 10: API dependency detection."""

import pytest

from models.api_models import (
    APIEndpoint,
    APIParameter,
    APIResponseDefinition,
    APISpecification,
    HTTPMethod,
    ParameterLocation,
)
from models.dependency import (
    APIDependency,
    DependencyType,
    VariableSourceLocation,
)
from openapi.dependency_detector import DependencyDetector
from openapi.parser import OpenAPIParser


def test_dependency_models_validation() -> None:
    dep = APIDependency(
        producer_method=HTTPMethod.POST,
        producer_path="/auth",
        consumer_method=HTTPMethod.GET,
        consumer_path="/booking",
        dependency_type=DependencyType.AUTHENTICATION,
        variable_name="token",
        extraction_path="token",
        target_parameter="Authorization",
        target_location=ParameterLocation.HEADER,
        confidence=0.95,
        evidence=["POST /auth produces token in response", "GET /booking consumes Authorization header"],
        is_deterministic=True,
    )
    assert dep.producer_method == HTTPMethod.POST
    assert dep.producer_path == "/auth"
    assert dep.confidence == 0.95

    with pytest.raises(ValueError):
        # Path must be relative starting with /
        APIDependency(
            producer_method=HTTPMethod.POST,
            producer_path="auth",
            consumer_method=HTTPMethod.GET,
            consumer_path="/booking",
            dependency_type=DependencyType.AUTHENTICATION,
            variable_name="token",
            extraction_path="token",
            target_parameter="Authorization",
            target_location=ParameterLocation.HEADER,
            confidence=0.95,
            evidence=["some evidence"],
        )


def test_detect_resource_lifecycle_dependencies_from_spec() -> None:
    # Build a spec with POST /booking (creates, returns bookingid)
    # and GET /booking/{booking_id}, PUT /booking/{booking_id}, DELETE /booking/{booking_id}
    spec = APISpecification(
        title="Booking API",
        version="1.0.0",
        openapi_version="3.0.3",
        endpoints=[
            APIEndpoint(
                method=HTTPMethod.POST,
                path="/booking",
                summary="Create booking",
                responses=[
                    APIResponseDefinition(
                        status_code="200",
                        description="Created",
                        schema={
                            "type": "object",
                            "properties": {
                                "bookingid": {"type": "integer"},
                                "booking": {"type": "object"},
                            },
                        },
                    )
                ],
            ),
            APIEndpoint(
                method=HTTPMethod.GET,
                path="/booking/{booking_id}",
                summary="Get booking",
                parameters=[
                    APIParameter(
                        name="booking_id",
                        location=ParameterLocation.PATH,
                        required=True,
                        schema={"type": "integer"},
                    )
                ],
                responses=[APIResponseDefinition(status_code="200", description="Found")],
            ),
            APIEndpoint(
                method=HTTPMethod.DELETE,
                path="/booking/{booking_id}",
                summary="Delete booking",
                parameters=[
                    APIParameter(
                        name="booking_id",
                        location=ParameterLocation.PATH,
                        required=True,
                        schema={"type": "integer"},
                    )
                ],
                responses=[APIResponseDefinition(status_code="201", description="Deleted")],
            ),
        ],
    )

    detector = DependencyDetector()
    graph = detector.detect_dependencies(spec)

    assert len(graph.dependencies) >= 2
    # Verify POST /booking -> GET /booking/{booking_id}
    post_to_get = next(
        (d for d in graph.dependencies if d.consumer_method == HTTPMethod.GET), None
    )
    assert post_to_get is not None
    assert post_to_get.producer_method == HTTPMethod.POST
    assert post_to_get.producer_path == "/booking"
    assert post_to_get.consumer_path == "/booking/{booking_id}"
    assert post_to_get.dependency_type == DependencyType.RESOURCE_LIFECYCLE
    assert post_to_get.variable_name == "bookingid"
    assert post_to_get.target_parameter == "booking_id"
    assert post_to_get.confidence >= 0.85
    assert len(post_to_get.evidence) > 0

    # Verify POST /booking -> DELETE /booking/{booking_id}
    post_to_del = next(
        (d for d in graph.dependencies if d.consumer_method == HTTPMethod.DELETE), None
    )
    assert post_to_del is not None
    assert post_to_del.producer_method == HTTPMethod.POST
    assert post_to_del.consumer_path == "/booking/{booking_id}"


def test_detect_auth_token_dependency() -> None:
    # POST /auth returns token, GET /secret requires auth
    spec = APISpecification(
        title="Auth API",
        version="1.0.0",
        openapi_version="3.0.3",
        endpoints=[
            APIEndpoint(
                method=HTTPMethod.POST,
                path="/auth",
                summary="Login endpoint",
                responses=[
                    APIResponseDefinition(
                        status_code="200",
                        description="Auth response",
                        schema={
                            "type": "object",
                            "properties": {
                                "token": {"type": "string"},
                            },
                        },
                    )
                ],
            ),
            APIEndpoint(
                method=HTTPMethod.GET,
                path="/secret",
                summary="Secret data",
                authentication_required=True,
                responses=[APIResponseDefinition(status_code="200", description="OK")],
            ),
        ],
    )

    detector = DependencyDetector()
    graph = detector.detect_dependencies(spec)

    auth_deps = [d for d in graph.dependencies if d.dependency_type == DependencyType.AUTHENTICATION]
    assert len(auth_deps) == 1
    dep = auth_deps[0]
    assert dep.producer_path == "/auth"
    assert dep.consumer_path == "/secret"
    assert dep.variable_name == "token"
    assert dep.target_location == ParameterLocation.HEADER


def test_detect_dependencies_on_sample_yaml() -> None:
    parser = OpenAPIParser()
    spec = parser.parse_file("tests/fixtures/sample_openapi.yaml")

    detector = DependencyDetector()
    graph = detector.detect_dependencies(spec)

    assert len(graph.dependencies) >= 1
    dep = graph.dependencies[0]
    assert dep.producer_path == "/booking"
    assert dep.consumer_path == "/booking/{booking_id}"
    assert dep.variable_name == "bookingid"


def test_dependency_detector_query_param_association() -> None:
    spec = APISpecification(
        title="Query Association API",
        version="1.0.0",
        openapi_version="3.0.3",
        endpoints=[
            APIEndpoint(
                method=HTTPMethod.POST,
                path="/users",
                responses=[
                    APIResponseDefinition(
                        status_code="201",
                        description="Created",
                        schema={
                            "type": "object",
                            "properties": {
                                "user_id": {"type": "string"},
                            },
                        },
                    )
                ],
            ),
            APIEndpoint(
                method=HTTPMethod.GET,
                path="/users/orders",
                parameters=[
                    APIParameter(
                        name="user_id",
                        location=ParameterLocation.QUERY,
                        required=True,
                        schema={"type": "string"},
                    )
                ],
                responses=[APIResponseDefinition(status_code="200", description="OK")],
            ),
        ],
    )
    detector = DependencyDetector()
    graph = detector.detect_dependencies(spec)
    assert any(d.target_location == ParameterLocation.QUERY for d in graph.dependencies)

