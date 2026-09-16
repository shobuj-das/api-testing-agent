"""Generic project profile and configuration loader for cross-project API testing."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from config.settings import Environment


class ProjectAuthConfig(BaseModel):
    """Configuration for automated login/authentication steps."""

    model_config = ConfigDict(extra="allow", strict=False)

    endpoint: str = "/auth"
    method: str = "POST"
    payload: dict[str, Any] = Field(default_factory=dict)
    token_json_path: str = "token"
    token_header_name: str = "Authorization"
    token_header_prefix: str = "Bearer "
    cookie_name: str | None = None


class ProjectConfig(BaseModel):
    """Reusable project configuration enabling testing of any API without codebase changes."""

    model_config = ConfigDict(extra="allow", strict=False)

    project_name: str = "API Testing Project"
    spec_path: str | None = None
    spec_url: str | None = None
    base_url: str = ""
    environment: Environment = Environment.STAGING
    allow_production_execution: bool = False
    api_timeout: float = 15.0
    llm_provider: str = "mock"
    llm_model: str | None = None
    default_headers: dict[str, str] = Field(default_factory=dict)
    auth: ProjectAuthConfig | None = None
    initial_variables: dict[str, Any] = Field(default_factory=dict)
    include_endpoints: list[str] = Field(default_factory=list)
    exclude_endpoints: list[str] = Field(default_factory=list)
    max_tests: int = 50
    max_iterations: int = 25
    max_retries: int = 1
    execute_workflows: bool = True
    auto_approve: bool = False

    # LLM Settings
    llm_api_key: str | None = None
    llm_temperature: float = 0.2
    llm_max_tokens: int = 4096
    llm_base_url: str | None = None

    # Notification
    discord_webhook_url: str | None = None
    discord_mention_role: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    notify_on_success: bool = False

    @classmethod
    def from_file(cls, config_path: str | Path) -> "ProjectConfig":
        """Load configuration from a YAML or JSON file."""
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Project configuration file not found: {path}")
        content = path.read_text(encoding="utf-8")
        data = (
            json.loads(content)
            if path.suffix.lower() == ".json"
            else yaml.safe_load(content)
        )
        if not isinstance(data, dict):
            raise ValueError("Configuration file must contain a key-value mapping.")
        return cls.model_validate(data)

    def to_file(self, config_path: str | Path) -> None:
        """Save configuration to a YAML or JSON file."""
        path = Path(config_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self.model_dump(mode="json")
        if path.suffix.lower() == ".json":
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        else:
            path.write_text(yaml.dump(data, sort_keys=False), encoding="utf-8")
