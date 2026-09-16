"""Tests for configuration safety."""

import pytest

from config.settings import ConfigurationError, Environment, Settings


def test_production_requires_explicit_opt_in() -> None:
    settings = Settings(api_base_url="https://example.test", environment=Environment.PRODUCTION)

    with pytest.raises(ConfigurationError, match="Production execution is disabled"):
        settings.assert_execution_allowed()


def test_non_production_is_allowed() -> None:
    Settings(api_base_url="https://example.test", environment=Environment.STAGING).assert_execution_allowed()
