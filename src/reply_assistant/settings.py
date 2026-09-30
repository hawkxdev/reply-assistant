"""Settings from the environment."""

from pathlib import Path
from typing import Any

from pydantic import SecretStr, ValidationError, model_validator
from pydantic_core import InitErrorDetails, PydanticCustomError
from pydantic_settings import BaseSettings, SettingsConfigDict

# === Settings ===

_FALLBACK_FIELDS = (
    'fallback_provider_api_key',
    'fallback_provider_base_url',
    'fallback_provider_model',
)


def _partial_fallback_error() -> ValidationError:
    """Error without setting values."""
    line: InitErrorDetails = {
        'type': PydanticCustomError(
            'partial_fallback', 'the fallback provider settings must be set together'
        ),
        'loc': (),
        'input': None,
    }
    return ValidationError.from_exception_data('Settings', [line])


class Settings(BaseSettings):
    """Service deployment settings."""

    model_config = SettingsConfigDict(
        env_file='.env',
        env_prefix='REPLY_ASSISTANT_',
        env_ignore_empty=True,
        extra='ignore',
    )

    provider_api_key: SecretStr
    provider_base_url: str
    provider_model: str
    kb_path: Path
    fallback_provider_api_key: SecretStr | None = None
    fallback_provider_base_url: str | None = None
    fallback_provider_model: str | None = None
    fallback_provider_json_mode: bool = True

    @model_validator(mode='before')
    @classmethod
    def fallback_settings_come_together(cls, data: Any) -> Any:
        """Reject a partial fallback."""
        if isinstance(data, dict):
            given = [data.get(name) is not None for name in _FALLBACK_FIELDS]
            if any(given) and not all(given):
                raise _partial_fallback_error()
        return data
