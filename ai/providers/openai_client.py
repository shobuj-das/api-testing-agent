"""OpenAI-compatible LLM adapter."""
from __future__ import annotations

from ai.llm_client import LLMClient, LLMProviderError, LLMResponse

class OpenAILLMClient(LLMClient):
    """Adapter for OpenAI Chat Completions API."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gpt-4o",
        base_url: str | None = None,   # For Azure / vLLM / LMStudio
        max_structured_retries: int = 1,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> None:
        super().__init__(max_structured_retries=max_structured_retries)
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise LLMProviderError(
                "openai package is not installed. Run: pip install openai"
            ) from exc
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    def _generate(self, prompt: str, *, system_prompt: str | None = None) -> LLMResponse:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            )
        except Exception as exc:
            raise LLMProviderError(f"OpenAI API error: {exc}") from exc
        choice = response.choices[0]
        usage = response.usage
        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            input_tokens=usage.prompt_tokens if usage else None,
            output_tokens=usage.completion_tokens if usage else None,
        )
