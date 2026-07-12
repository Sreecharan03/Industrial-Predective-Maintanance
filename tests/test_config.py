"""Config: fail-fast validation of environment-driven settings."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from senseminds.config.settings import Settings


def test_defaults_are_valid() -> None:
    settings = Settings()
    assert settings.environment == "local"
    assert settings.log_level == "INFO"


def test_log_level_is_normalized_and_validated() -> None:
    assert Settings(log_level="debug").log_level == "DEBUG"
    with pytest.raises(ValidationError):
        Settings(log_level="verbose")


def test_environment_is_validated() -> None:
    assert Settings(environment="PROD").environment == "prod"
    with pytest.raises(ValidationError):
        Settings(environment="production")


def test_settings_are_frozen() -> None:
    settings = Settings()
    with pytest.raises(ValidationError):
        settings.environment = "dev"  # type: ignore[misc]
