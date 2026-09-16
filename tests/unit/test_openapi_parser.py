"""Tests for OpenAPI 3 parsing and deterministic analysis."""

from pathlib import Path

import pytest

from openapi.analyzer import OpenAPIAnalyzer
from openapi.parser import OpenAPIParseError, OpenAPIParser


FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_openapi.yaml"


def test_parser_extracts_endpoints_parameters_schemas_and_authentication() -> None:
    specification = OpenAPIParser().parse_file(FIXTURE)

    assert specification.title == "Booking API"
    assert len(specification.endpoints) == 2
    create = next(endpoint for endpoint in specification.endpoints if endpoint.operation_id == "createBooking")
    assert create.method == "POST"
    assert create.authentication_required is False
    assert create.parameters[0].name == "locale"
    assert create.request_body_schema is not None
    assert create.request_body_schema["required"] == ["firstname", "lastname"]
    assert create.responses[0].status_code == "200"


def test_operation_inherits_global_auth_and_extracts_path_parameter() -> None:
    specification = OpenAPIParser().parse_file(FIXTURE)
    get_booking = next(endpoint for endpoint in specification.endpoints if endpoint.method == "GET")

    assert get_booking.authentication_required is True
    assert get_booking.parameters[0].schema_definition == {"type": "integer"}


def test_analyzer_reports_only_deterministic_endpoint_facts() -> None:
    specification = OpenAPIParser().parse_file(FIXTURE)
    create = next(endpoint for endpoint in specification.endpoints if endpoint.method == "POST")

    analysis = OpenAPIAnalyzer().analyze_endpoint(create)

    assert analysis.required_inputs == ("body:firstname", "body:lastname")
    assert "body:totalprice" in analysis.optional_inputs
    assert analysis.documented_status_codes == ("200",)


def test_parser_rejects_openapi_2_documents() -> None:
    with pytest.raises(OpenAPIParseError, match="Only OpenAPI 3"):
        OpenAPIParser().parse_document({"swagger": "2.0", "info": {}, "paths": {}})


def test_parser_rejects_unresolvable_references() -> None:
    document = {
        "openapi": "3.0.0", "info": {"title": "Test", "version": "1"},
        "paths": {"/items": {"get": {"responses": {"200": {"$ref": "#/components/responses/Missing"}}}}},
    }
    with pytest.raises(OpenAPIParseError, match="Unresolvable"):
        OpenAPIParser().parse_document(document)
