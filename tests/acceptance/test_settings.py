"""Acceptance tests for issue 7."""

import importlib
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

pytestmark = pytest.mark.xfail(strict=True, reason='issue 7 is not implemented')

PREFIX = 'REPLY_ASSISTANT_'
ENVIRONMENT = {
    'REPLY_ASSISTANT_PROVIDER_API_KEY': 'environment-key',
    'REPLY_ASSISTANT_PROVIDER_BASE_URL': 'https://environment.example/v1',
    'REPLY_ASSISTANT_PROVIDER_MODEL': 'environment-model',
    'REPLY_ASSISTANT_KB_PATH': 'environment/kb.yaml',
}
DOTENV = {
    'REPLY_ASSISTANT_PROVIDER_API_KEY': 'dotenv-key',
    'REPLY_ASSISTANT_PROVIDER_BASE_URL': 'https://dotenv.example/v1',
    'REPLY_ASSISTANT_PROVIDER_MODEL': 'dotenv-model',
    'REPLY_ASSISTANT_KB_PATH': 'dotenv/kb.yaml',
}
FIELDS = ['provider_api_key', 'provider_base_url', 'provider_model', 'kb_path']
ENV_EXAMPLE = Path(__file__).parents[2] / '.env.example'


@pytest.fixture
def settings_class() -> Any:
    """Provide the settings class."""
    return importlib.import_module('reply_assistant.settings').Settings


@pytest.fixture(autouse=True)
def empty_sources(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Remove every settings source."""
    monkeypatch.chdir(tmp_path)
    for name in ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)


def fill_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set every variable in the environment."""
    for name, value in ENVIRONMENT.items():
        monkeypatch.setenv(name, value)


def write_dotenv(directory: Path) -> None:
    """Write every variable to a dotenv file."""
    lines = [f'{name}={value}' for name, value in DOTENV.items()]
    (directory / '.env').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def env_example_entries() -> dict[str, str]:
    """Read the variables of the example file."""
    lines = ENV_EXAMPLE.read_text(encoding='utf-8').splitlines()
    pairs = [line.split('=', 1) for line in lines if '=' in line and line[0] != '#']
    return {name.strip(): value.strip() for name, value in pairs}


def rejected_fields(error: ValidationError) -> set[tuple[str, str]]:
    """Collect the rejected fields with the error types."""
    return {(str(item['loc'][0]), item['type']) for item in error.errors()}


def test_settings_are_read_from_prefixed_environment(
    settings_class: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    fill_environment(monkeypatch)

    settings = settings_class()

    assert isinstance(settings.provider_api_key, SecretStr)
    assert settings.provider_api_key.get_secret_value() == 'environment-key'
    assert settings.provider_base_url == 'https://environment.example/v1'
    assert settings.provider_model == 'environment-model'
    assert settings.kb_path == Path('environment/kb.yaml')


def test_settings_are_read_from_dotenv_in_working_directory(
    settings_class: Any, tmp_path: Path
) -> None:
    write_dotenv(tmp_path)

    settings = settings_class()

    assert settings.provider_api_key.get_secret_value() == 'dotenv-key'
    assert settings.provider_base_url == 'https://dotenv.example/v1'
    assert settings.provider_model == 'dotenv-model'
    assert settings.kb_path == Path('dotenv/kb.yaml')


def test_environment_wins_over_dotenv(
    settings_class: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    write_dotenv(tmp_path)
    monkeypatch.setenv('REPLY_ASSISTANT_PROVIDER_MODEL', 'environment-model')

    settings = settings_class()

    assert settings.provider_model == 'environment-model'
    assert settings.provider_base_url == 'https://dotenv.example/v1'


@pytest.mark.parametrize('field', FIELDS)
def test_missing_variable_is_rejected(
    settings_class: Any, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    fill_environment(monkeypatch)
    monkeypatch.delenv(PREFIX + field.upper())

    with pytest.raises(ValidationError) as caught:
        settings_class()

    assert rejected_fields(caught.value) == {(field, 'missing')}


@pytest.mark.parametrize('field', FIELDS)
def test_empty_variable_is_rejected(
    settings_class: Any, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    fill_environment(monkeypatch)
    monkeypatch.setenv(PREFIX + field.upper(), '')

    with pytest.raises(ValidationError) as caught:
        settings_class()

    assert rejected_fields(caught.value) == {(field, 'missing')}


def test_provider_key_is_hidden_in_text_forms(
    settings_class: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    fill_environment(monkeypatch)

    settings = settings_class()

    assert 'environment-model' in repr(settings)
    assert 'environment-key' not in repr(settings)
    assert 'environment-key' not in str(settings)
    assert 'environment-key' not in settings.model_dump_json()


def test_env_example_names_every_setting(settings_class: Any) -> None:
    expected = {PREFIX + name.upper() for name in settings_class.model_fields}

    assert expected == set(ENVIRONMENT)
    assert set(env_example_entries()) == expected


def test_env_example_holds_no_value(settings_class: Any) -> None:
    entries = env_example_entries()

    assert len(entries) == len(settings_class.model_fields)
    assert set(entries.values()) == {''}
