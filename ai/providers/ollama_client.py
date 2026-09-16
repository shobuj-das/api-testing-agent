"""Ollama local model adapter (free, no API key needed)."""
from __future__ import annotations

import json
from ai.llm_client import LLMClient, LLMProviderError, LLMResponse

class OllamaLLMClient(LLMClient):
    """Adapter for Ollama local models via HTTP API."""

    def __init__(
        self,
        *,
        model: str = "llama3.1",
        base_url: str = "http://localhost:11434",
        max_structured_retries: int = 2,
        temperature: float = 0.2,
    ) -> None:
        super().__init__(max_structured_retries=max_structured_retries)
        try:
            import requests
        except ImportError as exc:
            raise LLMProviderError("requests is required for Ollama.") from exc
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._temperature = temperature
        self._requests = requests

    def _generate(self, prompt: str, *, system_prompt: str | None = None) -> LLMResponse:
        payload = {
            "model": self._model,
            "messages": [],
            "stream": False,
            "options": {"temperature": self._temperature},
        }
        if system_prompt:
            payload["messages"].append({"role": "system", "content": system_prompt})
        payload["messages"].append({"role": "user", "content": prompt})
        try:
            resp = self._requests.post(
                f"{self._base_url}/api/chat",
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
        except Exception as exc:
            raise LLMProviderError(f"Ollama API error: {exc}") from exc
        data = resp.json()
        content = data.get("message", {}).get("content", "")
        return LLMResponse(
            content=content,
            model=self._model,
            input_tokens=data.get("prompt_eval_count"),
            output_tokens=data.get("eval_count"),
        )
