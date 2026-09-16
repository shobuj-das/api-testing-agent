"""Environment-backed settings and production-execution safeguards."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


class ConfigurationError(ValueError):
    """Raised when runtime configuration is invalid or unsafe."""


class Environment(StrEnum):
    LOCAL = "local"
    DEV = "dev"
    STAGING = "staging"
    PRODUCTION = "production"


def _as_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    """Application settings loaded from environment variables."""

    api_base_url: str = ""
    api_username: str | None = None
    api_password: str | None = None
    api_bearer_token: str | None = None
    api_timeout: float = 15.0
    environment: Environment = Environment.STAGING
    allow_production_execution: bool = False
    llm_provider: str = "mock"
    llm_model: str | None = None
    llm_api_key: str | None = None
    max_agent_iterations: int = 25
    max_retries: int = 1

    @classmethod
    def from_environment(cls) -> "Settings":
        """Load settings, optionally reading a local .env file first."""
        load_dotenv(Path(".env"), override=False)
        try:
            environment = Environment(os.getenv("API_ENVIRONMENT", "staging").lower())
        except ValueError as exc:
            valid = ", ".join(item.value for item in Environment)
            raise ConfigurationError(f"API_ENVIRONMENT must be one of: {valid}") from exc

        try:
            timeout = float(os.getenv("API_TIMEOUT", "15"))
            max_iterations = int(os.getenv("MAX_AGENT_ITERATIONS", "25"))
            max_retries = int(os.getenv("MAX_RETRIES", "1"))
        except ValueError as exc:
            raise ConfigurationError("Timeout and agent limits must be numeric.") from exc
        if timeout <= 0 or max_iterations <= 0 or max_retries < 0:
            raise ConfigurationError("Timeout/iterations must be positive; retries cannot be negative.")

        return cls(
            api_base_url=os.getenv("API_BASE_URL", "").rstrip("/"),
            api_username=os.getenv("API_USERNAME") or None,
            api_password=os.getenv("API_PASSWORD") or None,
            api_bearer_token=os.getenv("API_BEARER_TOKEN") or None,
            api_timeout=timeout,
            environment=environment,
            allow_production_execution=_as_bool(os.getenv("ALLOW_PRODUCTION_EXECUTION")),
            llm_provider=os.getenv("LLM_PROVIDER", "mock"),
            llm_model=os.getenv("LLM_MODEL") or None,
            llm_api_key=os.getenv("LLM_API_KEY") or None,
            max_agent_iterations=max_iterations,
            max_retries=max_retries,
        )

    def assert_execution_allowed(self) -> None:
        """Block production traffic unless deliberately enabled."""
        if self.environment is Environment.PRODUCTION and not self.allow_production_execution:
            raise ConfigurationError(
                "Production execution is disabled. Set ALLOW_PRODUCTION_EXECUTION=true explicitly."
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached process-wide settings for command-line entry points."""
    return Settings.from_environment()
