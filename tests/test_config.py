import os

import pytest
from pydantic import SecretStr, ValidationError

from ai_service.core.config import Settings


@pytest.fixture(autouse=True)
def clear_llm_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in tuple(os.environ):
        if name.lower().startswith("llm_"):
            monkeypatch.delenv(name)


def test_llm_settings_are_optional() -> None:
    settings = Settings(_env_file=None)
    assert settings.llm_api_key is None
    assert settings.llm_base_url is None
    assert settings.llm_model is None
    assert settings.llm_timeout == 30


def test_llm_settings_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-secret-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_TIMEOUT", "12.5")
    settings = Settings(_env_file=None)
    assert isinstance(settings.llm_api_key, SecretStr)
    assert settings.llm_api_key.get_secret_value() == "test-secret-key"
    assert str(settings.llm_base_url) == "https://provider.example/v1"
    assert settings.llm_model == "test-model"
    assert settings.llm_timeout == 12.5
    assert "test-secret-key" not in repr(settings)
    assert "test-secret-key" not in settings.model_dump_json()


@pytest.mark.parametrize("value", ["", "  "])
def test_empty_llm_configuration_is_unset(value: str) -> None:
    settings = Settings(_env_file=None, llm_api_key=value, llm_base_url=value, llm_model=value)
    assert settings.llm_api_key is None
    assert settings.llm_base_url is None
    assert settings.llm_model is None


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan")])
def test_invalid_llm_timeout(value: float) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, llm_timeout=value)


def test_invalid_llm_url() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, llm_base_url="not-a-url")
