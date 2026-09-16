"""Tests for provider isolation and strict LLM structured-output handling."""

import pytest

from ai.llm_client import LLMProviderError, MockLLMClient, StructuredOutputError, create_llm_client
from config.settings import Settings
from models.test_plan import TestPlan as ApiTestPlan


VALID_PLAN = {
    "name": "Booking smoke tests",
    "objective": "Validate the booking API",
    "test_cases": [],
    "reasoning_summary": "No tests requested in this mock response.",
    "source": "mock",
}


def test_mock_client_validates_structured_output() -> None:
    client = MockLLMClient([VALID_PLAN])

    plan = client.generate_structured("Generate a test plan.", ApiTestPlan)

    assert plan.name == "Booking smoke tests"
    assert client.metrics.call_count == 1
    assert client.calls[0][1] is not None


def test_invalid_output_uses_one_correction_attempt() -> None:
    client = MockLLMClient(["not json", VALID_PLAN], max_structured_retries=1)

    plan = client.generate_structured("Generate a test plan.", ApiTestPlan)

    assert plan.source == "mock"
    assert client.metrics.call_count == 2
    assert "previous structured response was rejected" in client.calls[1][0].lower()


def test_invalid_output_fails_safely_after_retry_limit() -> None:
    client = MockLLMClient(["[]", "{}"], max_structured_retries=1)

    with pytest.raises(StructuredOutputError) as error:
        client.generate_structured("Generate a test plan.", ApiTestPlan)

    assert len(error.value.raw_responses) == 2


def test_mock_client_never_invents_a_response() -> None:
    with pytest.raises(LLMProviderError, match="no configured response"):
        MockLLMClient().generate("Hello")


def test_factory_rejects_uninstalled_provider() -> None:
    settings = Settings(api_base_url="https://example.test", llm_provider="unavailable")

    with pytest.raises(LLMProviderError, match="not installed"):
        create_llm_client(settings)
