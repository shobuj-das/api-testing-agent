"""Tests for deterministic HTTP client behavior."""

from typing import Any

from clients.api_client import APIClient, mask_sensitive, mask_sensitive_text
from config.settings import Settings


class FakeResponse:
    status_code = 200
    headers = {"Content-Type": "application/json"}
    text = '{"bookingid": 42}'
    url = "https://example.test/booking/42"

    def json(self) -> dict[str, int]:
        return {"bookingid": 42}


class FakeSession:
    def __init__(self) -> None:
        self.request_arguments: dict[str, Any] = {}

    def request(self, **kwargs: Any) -> FakeResponse:
        self.request_arguments = kwargs
        return FakeResponse()


def test_client_resolves_path_and_captures_response() -> None:
    session = FakeSession()
    client = APIClient(Settings(api_base_url="https://example.test"), session=session)  # type: ignore[arg-type]

    response = client.get("/booking/{booking_id}", path_params={"booking_id": 42})

    assert session.request_arguments["url"] == "https://example.test/booking/42"
    assert response.status_code == 200
    assert response.json_body == {"bookingid": 42}
    assert response.duration_ms >= 0


def test_mask_sensitive_values_recursively() -> None:
    data = {"Authorization": "Bearer top-secret", "nested": {"password": "nope"}}

    assert mask_sensitive(data) == {
        "Authorization": "***MASKED***",
        "nested": {"password": "***MASKED***"},
    }


def test_mask_sensitive_text_redacts_common_log_formats() -> None:
    line = "Authorization: Bearer top-secret password=abc token:xyz"

    assert "top-secret" not in mask_sensitive_text(line)
    assert "abc" not in mask_sensitive_text(line)
    assert "xyz" not in mask_sensitive_text(line)
