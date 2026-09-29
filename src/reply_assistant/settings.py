"""Service settings read from the environment."""

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Deployment settings of the service."""

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
