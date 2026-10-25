# -*- coding: utf-8 -*-
"""Tests for runtime model configuration."""

from __future__ import annotations

import pytest

from agent.config import DEFAULT_BASE_URL, DEFAULT_MODEL, load_config


@pytest.fixture(autouse=True)
def clear_exhibit_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests independent from the developer's environment."""
    for name in (
        "EXHIBIT_API_KEY",
        "EXHIBIT_BASE_URL",
        "EXHIBIT_MODEL",
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

    with pytest.raises(ValueError, match="EXHIBIT_API_KEY is required"):
        load_config()


def test_defaults_use_remote_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXHIBIT_API_KEY", "test-key")

    config = load_config()

    assert config.base_url == DEFAULT_BASE_URL
    assert config.api_key == "test-key"
    assert config.model == DEFAULT_MODEL
    assert config.max_iters == 60
    assert config.request_timeout == 600


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
