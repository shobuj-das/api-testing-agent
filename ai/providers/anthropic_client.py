"""Anthropic Claude adapter."""
from __future__ import annotations

from ai.llm_client import LLMClient, LLMProviderError, LLMResponse

class AnthropicLLMClient(LLMClient):
    """Adapter for Anthropic Messages API."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        max_structured_retries: int = 1,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> None:
        super().__init__(max_structured_retries=max_structured_retries)
        try:
            import anthropic
        except ImportError as exc:
            raise LLMProviderError(
                "anthropic package is not installed. Run: pip install anthropic"
            ) from exc
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    def _generate(self, prompt: str, *, system_prompt: str | None = None) -> LLMResponse:
        kwargs = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        try:
            response = self._client.messages.create(**kwargs)
        except Exception as exc:
            raise LLMProviderError(f"Anthropic API error: {exc}") from exc
        content = response.content[0].text if response.content else ""
        return LLMResponse(
            content=content,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
