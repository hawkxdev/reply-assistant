"""Settings unit tests."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from reply_assistant.settings import Settings

# === Data ===

FIELDS = ['provider_api_key', 'provider_base_url', 'provider_model', 'kb_path']
PREFIX = 'REPLY_ASSISTANT_'

# === Fixtures and helpers ===


@pytest.fixture(autouse=True)
def clean_sources(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Remove every settings source."""
    monkeypatch.chdir(tmp_path)
    for field in FIELDS:
        monkeypatch.delenv(PREFIX + field.upper(), raising=False)


def rejected_fields(error: ValidationError) -> set[tuple[str, str]]:
    """Rejected fields with types."""
    return {(str(item['loc'][0]), item['type']) for item in error.errors()}


# === Tests ===


def test_empty_dotenv_value_counts_as_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(PREFIX + 'PROVIDER_API_KEY', 'unit-key')
    monkeypatch.setenv(PREFIX + 'PROVIDER_BASE_URL', 'https://unit.example/v1')
    monkeypatch.setenv(PREFIX + 'KB_PATH', 'unit/kb.yaml')
    (tmp_path / '.env').write_text(f'{PREFIX}PROVIDER_MODEL=\n', encoding='utf-8')

    with pytest.raises(ValidationError) as caught:
        Settings()

    assert rejected_fields(caught.value) == {('provider_model', 'missing')}


def test_dotenv_extra_variables_are_ignored(tmp_path: Path) -> None:
    (tmp_path / '.env').write_text(
        f'{PREFIX}PROVIDER_API_KEY=file-key\n'
        f'{PREFIX}PROVIDER_BASE_URL=https://file.example/v1\n'
        f'{PREFIX}PROVIDER_MODEL=file-model\n'
        f'{PREFIX}KB_PATH=file/kb.yaml\n'
        f'{PREFIX}NOT_A_SETTING=y\n'
        'UNRELATED_NAME=zzz\n',
        encoding='utf-8',
    )

    settings = Settings()

    assert settings.provider_api_key.get_secret_value() == 'file-key'
    assert settings.provider_base_url == 'https://file.example/v1'
    assert settings.provider_model == 'file-model'
    assert settings.kb_path == Path('file/kb.yaml')
