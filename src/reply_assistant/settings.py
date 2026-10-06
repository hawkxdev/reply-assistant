"""Settings from the environment."""

from pathlib import Path
from typing import Any, Self

from pydantic import Field, SecretStr, ValidationError, model_validator
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


def _kb_source_error(field: str, code: str, message: str) -> ValidationError:
    """Error on one knowledge source."""
    line: InitErrorDetails = {
        'type': PydanticCustomError(code, message),
        'loc': (field,),
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
    kb_path: Path | None = None
    kb_registry: Path | None = None
    demo_catalogues: dict[str, str] = Field(default_factory=dict)
    api_token: SecretStr | None = None
    fallback_provider_api_key: SecretStr | None = None
    fallback_provider_base_url: str | None = None
    fallback_provider_model: str | None = None
    fallback_provider_json_mode: bool = True
    provider_max_output_tokens: int | None = Field(default=None, gt=0)

    @model_validator(mode='before')
    @classmethod
    def exactly_one_kb_source(cls, data: Any) -> Any:
        """Require one knowledge source."""
        if isinstance(data, dict):
            has_path = data.get('kb_path') is not None
            has_registry = data.get('kb_registry') is not None
            if has_path and has_registry:
                raise _kb_source_error(
                    'kb_registry',
                    'both_kb_sources',
                    'set either kb_path or kb_registry',
                )
            if not has_path and not has_registry:
                raise _kb_source_error(
                    'kb_path', 'missing_kb_source', 'set kb_path or kb_registry'
                )
        return data

    @model_validator(mode='before')
    @classmethod
    def fallback_settings_come_together(cls, data: Any) -> Any:
        """Reject a partial fallback."""
        if isinstance(data, dict):
            given = [data.get(name) is not None for name in _FALLBACK_FIELDS]
            if any(given) and not all(given):
                raise _partial_fallback_error()
        return data

    @model_validator(mode='after')
    def complete_demo_catalogues(self) -> Self:
        """Validate demo language mappings."""
        if self.demo_catalogues and (
            set(self.demo_catalogues) != {'en', 'ru'}
            or self.kb_registry is None
            or any(
                not value or value.strip() != value
                for value in self.demo_catalogues.values()
            )
        ):
            raise _kb_source_error(
                'demo_catalogues',
                'invalid_demo_catalogues',
                'demo catalogues require both language mappings and a registry',
            )
        return self
