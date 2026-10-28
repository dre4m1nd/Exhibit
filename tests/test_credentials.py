# -*- coding: utf-8 -*-
"""Tests for local model provider credential storage."""

from __future__ import annotations

import json

import pytest

from agent.credentials import (
    CONFIG_ENV,
    load_credentials,
    remove_credential,
    save_credential,
)
from agent.providers import PROVIDERS, get_provider, validate_base_url


@pytest.fixture(autouse=True)
def credential_dir(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(CONFIG_ENV, str(tmp_path))
    return tmp_path


def test_provider_catalog_contains_required_providers() -> None:
    assert set(PROVIDERS) == {"openai", "deepseek", "qwen", "openrouter", "custom"}
    assert get_provider("qwen").base_url.startswith("https://dashscope.")
    assert get_provider("openrouter").base_url == "https://openrouter.ai/api/v1"
    assert get_provider("openrouter").models == ("openrouter/free",)
    assert get_provider("custom").base_url == ""


def test_unknown_provider_lists_choices() -> None:
    with pytest.raises(KeyError, match="openai"):
        get_provider("missing")


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://api.example.com/v1",
        "https://localhost/v1",
        "https://127.0.0.1/v1",
        "https://user:pass@api.example.com/v1",
    ],
)
def test_unsafe_endpoints_are_rejected(endpoint: str) -> None:
    with pytest.raises(ValueError):
        validate_base_url(endpoint)


def test_custom_provider_accepts_loopback_endpoints() -> None:
    assert (
        validate_base_url("http://127.0.0.1:3425/v1", provider="custom")
        == "http://127.0.0.1:3425/v1"
    )
    assert (
        validate_base_url("https://[::1]:3425/v1/", provider="custom")
        == "https://[::1]:3425/v1"
    )


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://127.0.0.1:3425/v1",
        "https://127.0.0.1:3425/v1",
    ],
)
def test_builtin_provider_rejects_loopback_endpoints(endpoint: str) -> None:
    with pytest.raises(ValueError):
        validate_base_url(endpoint, provider="openai")


def test_save_and_mask_credential(credential_dir) -> None:
    saved = save_credential("deepseek", "sk-test-1234567890")

    assert saved.model == "deepseek-chat"
    assert saved.masked().endswith("sk-t…7890")
    stored = json.loads((credential_dir / "credentials.json").read_text("utf-8"))
    assert stored["providers"]["deepseek"]["api_key"] == "sk-test-1234567890"
    assert load_credentials()["deepseek"].model == "deepseek-chat"


def test_custom_model_and_endpoint_are_kept() -> None:
    saved = save_credential(
        "openai",
        "sk-test-abcdefghij",
        model="custom-model",
        base_url="https://gateway.example.com/v1/",
    )

    assert saved.base_url == "https://gateway.example.com/v1"
    assert saved.model == "custom-model"


def test_custom_provider_requires_endpoint_and_model() -> None:
    with pytest.raises(ValueError, match="base URL"):
        save_credential("custom", "sk-test-abcdefghij")
    with pytest.raises(ValueError, match="model"):
        save_credential(
            "custom",
            "sk-test-abcdefghij",
            base_url="https://models.example.com/v1",
        )

    saved = save_credential(
        "custom",
        "sk-test-abcdefghij",
        model="custom-model",
        base_url="https://models.example.com/v1",
    )
    assert saved.provider == "custom"


def test_remove_credential() -> None:
    save_credential("qwen", "sk-test-abcdefghij")
    assert remove_credential("qwen") is True
    assert "qwen" not in load_credentials()
    assert remove_credential("qwen") is False


def test_empty_api_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="API key"):
        save_credential("openai", "   ")
