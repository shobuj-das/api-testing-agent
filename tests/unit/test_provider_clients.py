"""Unit tests for the LLM provider clients."""
import pytest
from ai.llm_client import create_llm_client, LLMProviderError
from ai.auto_mock_client import AutoMockLLMClient
from config.settings import Settings

def test_create_llm_client_mock():
    """Test factory creates mock client."""
    settings = Settings(llm_provider="mock", environment="local")
    client = create_llm_client(settings)
    assert client is not None

def test_create_llm_client_unsupported():
    """Test factory raises on unsupported provider."""
    settings = Settings(llm_provider="invalid_provider", environment="local")
    with pytest.raises(LLMProviderError, match="not supported"):
        create_llm_client(settings)

def test_create_llm_client_openai_missing_key():
    """Test OpenAI provider missing API key."""
    settings = Settings(llm_provider="openai", environment="local")
    with pytest.raises(LLMProviderError, match="LLM_API_KEY is required"):
        create_llm_client(settings)

def test_create_llm_client_anthropic_missing_key():
    """Test Anthropic provider missing API key."""
    settings = Settings(llm_provider="anthropic", environment="local")
    with pytest.raises(LLMProviderError, match="LLM_API_KEY is required"):
        create_llm_client(settings)
