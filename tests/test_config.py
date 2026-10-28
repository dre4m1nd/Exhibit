# -*- coding: utf-8 -*-
"""Tests for runtime model configuration."""

from __future__ import annotations

import pytest

from agent.config import DEFAULT_BASE_URL, DEFAULT_MODEL, load_config
from agent.credentials import CONFIG_ENV, save_credential


@pytest.fixture(autouse=True)
def clear_exhibit_env(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests independent from the developer's environment."""
    monkeypatch.setenv(CONFIG_ENV, str(tmp_path / "config"))
    for name in (
        "EXHIBIT_API_KEY",
        "OPENROUTER_API_KEY",
        "EXHIBIT_BASE_URL",
        "EXHIBIT_MODEL",
        "EXHIBIT_PROVIDER",
        "EXHIBIT_MAX_ITERS",
        "EXHIBIT_TIMEOUT",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("api_key", [None, "", "   "])
def test_api_key_is_required(
    monkeypatch: pytest.MonkeyPatch,
    api_key: str | None,
) -> None:
    if api_key is not None:
        monkeypatch.setenv("EXHIBIT_API_KEY", api_key)

    with pytest.raises(
        ValueError,
        match="EXHIBIT_API_KEY or OPENROUTER_API_KEY is required",
    ):
        load_config()


def test_defaults_use_remote_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXHIBIT_API_KEY", "test-key")

    config = load_config()

    assert config.base_url == DEFAULT_BASE_URL
    assert config.api_key == "test-key"
    assert config.model == DEFAULT_MODEL
    assert config.max_iters == 60
    assert config.request_timeout == 600


def test_openrouter_key_selects_openrouter_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-env")

    config = load_config()

    assert config.base_url == "https://openrouter.ai/api/v1"
    assert config.api_key == "sk-or-env"
    assert config.model == "openrouter/free"


def test_exhibit_key_takes_precedence_over_openrouter_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EXHIBIT_API_KEY", "exhibit-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-key")

    config = load_config()

    assert config.base_url == DEFAULT_BASE_URL
    assert config.api_key == "exhibit-key"
    assert config.model == DEFAULT_MODEL


def test_valid_remote_configuration_is_loaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EXHIBIT_API_KEY", "test-key")
    monkeypatch.setenv("EXHIBIT_BASE_URL", "https://api.example.com/v1/")
    monkeypatch.setenv("EXHIBIT_MODEL", "review-model")
    monkeypatch.setenv("EXHIBIT_MAX_ITERS", "12")
    monkeypatch.setenv("EXHIBIT_TIMEOUT", "30.5")

    config = load_config()

    assert config.base_url == "https://api.example.com/v1"
    assert config.model == "review-model"
    assert config.max_iters == 12
    assert config.request_timeout == 30.5


def test_single_saved_credential_is_used_without_env_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_credential("deepseek", "sk-saved-1234567890")

    config = load_config()

    assert config.base_url == "https://api.deepseek.com/v1"
    assert config.api_key == "sk-saved-1234567890"
    assert config.model == "deepseek-chat"


def test_environment_overrides_saved_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_credential("deepseek", "sk-saved-1234567890")
    monkeypatch.setenv("EXHIBIT_API_KEY", "sk-env-1234567890")
    monkeypatch.setenv("EXHIBIT_MODEL", "env-model")

    config = load_config()

    assert config.base_url == DEFAULT_BASE_URL
    assert config.api_key == "sk-env-1234567890"
    assert config.model == "env-model"


def test_multiple_saved_providers_require_explicit_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_credential("openai", "sk-openai-1234567890")
    save_credential("deepseek", "sk-deepseek-1234567890")

    with pytest.raises(ValueError, match="EXHIBIT_PROVIDER"):
        load_config()

    monkeypatch.setenv("EXHIBIT_PROVIDER", "deepseek")
    config = load_config()
    assert config.api_key == "sk-deepseek-1234567890"
    assert config.model == "deepseek-chat"


def test_custom_endpoint_can_be_selected_explicitly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_credential(
        "openai",
        "sk-custom-1234567890",
        model="custom-model",
        base_url="https://gateway.example.com/v1",
    )
    monkeypatch.setenv("EXHIBIT_PROVIDER", "custom")

    config = load_config()

    assert config.base_url == "https://gateway.example.com/v1"
    assert config.model == "custom-model"


def test_custom_loopback_endpoint_can_be_selected_explicitly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EXHIBIT_PROVIDER", "custom")
    monkeypatch.setenv("EXHIBIT_API_KEY", "magpie")
    monkeypatch.setenv("EXHIBIT_BASE_URL", "http://127.0.0.1:3425/v1")
    monkeypatch.setenv("EXHIBIT_MODEL", "group/master")

    config = load_config()

    assert config.base_url == "http://127.0.0.1:3425/v1"
    assert config.model == "group/master"


def test_loopback_endpoint_requires_custom_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EXHIBIT_API_KEY", "magpie")
    monkeypatch.setenv("EXHIBIT_BASE_URL", "http://127.0.0.1:3425/v1")

    with pytest.raises(ValueError, match="must use https"):
        load_config()


@pytest.mark.parametrize(
    "base_url",
    [
        "http://api.example.com/v1",
        "https://localhost/v1",
        "https://localhost.localdomain/v1",
        "https://127.0.0.1:3425/v1",
        "https://10.0.0.1/v1",
        "https://172.16.0.1/v1",
        "https://192.168.1.10/v1",
        "https://169.254.1.1/v1",
        "https://[::1]/v1",
    ],
)
def test_non_remote_endpoints_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    base_url: str,
) -> None:
    monkeypatch.setenv("EXHIBIT_API_KEY", "test-key")
    monkeypatch.setenv("EXHIBIT_BASE_URL", base_url)

    with pytest.raises(ValueError):
        load_config()
