"""Google Gemini adapter."""
from __future__ import annotations

from ai.llm_client import LLMClient, LLMProviderError, LLMResponse

class GeminiLLMClient(LLMClient):
    """Adapter for Google Generative AI (Gemini) API."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gemini-2.5-flash",
        max_structured_retries: int = 1,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> None:
        super().__init__(max_structured_retries=max_structured_retries)
        try:
            import google.generativeai as genai
        except ImportError as exc:
            raise LLMProviderError(
                "google-generativeai is not installed. Run: pip install google-generativeai"
            ) from exc
        genai.configure(api_key=api_key)
        self._model_name = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._genai = genai

    def _generate(self, prompt: str, *, system_prompt: str | None = None) -> LLMResponse:
        model = self._genai.GenerativeModel(
            model_name=self._model_name,
            system_instruction=system_prompt,
            generation_config=self._genai.types.GenerationConfig(
                temperature=self._temperature,
                max_output_tokens=self._max_tokens,
            ),
        )
        try:
            response = model.generate_content(prompt)
        except Exception as exc:
            raise LLMProviderError(f"Gemini API error: {exc}") from exc
        usage = response.usage_metadata
        return LLMResponse(
            content=response.text or "",
            model=self._model_name,
            input_tokens=usage.prompt_token_count if usage else None,
            output_tokens=usage.candidates_token_count if usage else None,
        )
