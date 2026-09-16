"""Provider-neutral LLM interface with strict structured-output validation."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from ai.prompts import STRUCTURED_OUTPUT_SYSTEM_PROMPT, correction_prompt, structured_output_prompt
from config.settings import Settings

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


class LLMProviderError(RuntimeError):
    """Raised when a configured provider cannot be initialized or contacted."""


class StructuredOutputError(ValueError):
    """Raised only after all bounded attempts return invalid structured data."""

    def __init__(self, message: str, raw_responses: tuple[str, ...]) -> None:
        super().__init__(message)
        self.raw_responses = raw_responses


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """A provider response with optional usage metadata."""

    content: str
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(slots=True)
class LLMMetrics:
    """Lightweight provider-independent cost-control counters."""

    call_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def record(self, response: LLMResponse) -> None:
        self.call_count += 1
        self.input_tokens += response.input_tokens or 0
        self.output_tokens += response.output_tokens or 0


class LLMClient(ABC):
    """Abstraction boundary used by agents; it cannot run arbitrary commands or code."""

    def __init__(self, *, max_structured_retries: int = 1) -> None:
        if max_structured_retries < 0:
            raise ValueError("max_structured_retries cannot be negative.")
        self.max_structured_retries = max_structured_retries
        self.metrics = LLMMetrics()

    @abstractmethod
    def _generate(self, prompt: str, *, system_prompt: str | None = None) -> LLMResponse:
        """Provider-specific text generation implementation."""

    def generate(self, prompt: str, *, system_prompt: str | None = None) -> LLMResponse:
        """Generate text and record provider-reported usage, if present."""
        response = self._generate(prompt, system_prompt=system_prompt)
        self.metrics.record(response)
        return response

    def analyze(self, context: str, task: str) -> LLMResponse:
        """Request evidence-based analysis using the same provider boundary."""
        prompt = f"Context:\n{context}\n\nAnalysis task:\n{task}"
        return self.generate(prompt, system_prompt=STRUCTURED_OUTPUT_SYSTEM_PROMPT)

    def generate_structured(
        self,
        task: str,
        response_model: type[StructuredModel],
    ) -> StructuredModel:
        """Generate, validate, and bounded-retry a Pydantic object from JSON-only output."""
        prompt = structured_output_prompt(task, response_model)
        raw_responses: list[str] = []
        for attempt in range(self.max_structured_retries + 1):
            response = self.generate(prompt, system_prompt=STRUCTURED_OUTPUT_SYSTEM_PROMPT)
            raw_responses.append(response.content)
            try:
                payload = self._decode_json_object(response.content)
                # Re-serialize parsed JSON so Pydantic applies JSON validation semantics.
                # This accepts JSON representations such as enum strings while retaining
                # strict validation for direct Python object construction elsewhere.
                return response_model.model_validate_json(json.dumps(payload))
            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                if attempt == self.max_structured_retries:
                    raise StructuredOutputError(
                        f"Structured output remained invalid after {attempt + 1} attempt(s): {exc}",
                        tuple(raw_responses),
                    ) from exc
                prompt = correction_prompt(response_model, str(exc))
        raise AssertionError("Structured retry loop exited unexpectedly.")

    @staticmethod
    def _decode_json_object(content: str) -> dict[str, Any]:
        normalized = content.strip()
        if normalized.startswith("```"):
            lines = normalized.splitlines()
            if len(lines) < 3 or not lines[-1].strip().startswith("```"):
                raise ValueError("Response contains an incomplete Markdown code fence.")
            normalized = "\n".join(lines[1:-1]).strip()
        payload = json.loads(normalized)
        if not isinstance(payload, dict):
            raise ValueError("Structured output must be a JSON object.")
        return payload


class MockLLMClient(LLMClient):
    """Deterministic client for tests and offline framework development."""

    def __init__(
        self,
        responses: Iterable[str | dict[str, Any]] = (),
        *,
        max_structured_retries: int = 1,
    ) -> None:
        super().__init__(max_structured_retries=max_structured_retries)
        self._responses = iter(responses)
        self.calls: list[tuple[str, str | None]] = []

    def _generate(self, prompt: str, *, system_prompt: str | None = None) -> LLMResponse:
        self.calls.append((prompt, system_prompt))
        try:
            response = next(self._responses)
        except StopIteration as exc:
            raise LLMProviderError(
                "Mock LLM has no configured response. Supply sample responses for this task."
            ) from exc
        content = response if isinstance(response, str) else json.dumps(response)
        return LLMResponse(content=content, model="mock")


def create_llm_client(
    settings: Settings,
    *,
    mock_responses: Iterable[str | dict[str, Any]] = (),
) -> LLMClient:
    """Create a supported provider client without coupling agents to an SDK."""
    if settings.llm_provider.lower() == "mock":
        return MockLLMClient(mock_responses, max_structured_retries=settings.max_retries)
    raise LLMProviderError(
        f"LLM provider '{settings.llm_provider}' is not installed. "
        "Use LLM_PROVIDER=mock or add a provider adapter in a future milestone."
    )
