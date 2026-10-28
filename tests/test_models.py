# -*- coding: utf-8 -*-
"""Tests for provider model discovery and persistence."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError

import pytest

from agent.credentials import CONFIG_ENV, load_credentials, save_credential
from agent.models import _failure_message, discover_model_catalog, discover_models
from agent.session import SessionStore, switch_model, switch_model_provider


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CONFIG_ENV, str(tmp_path))


def test_catalog_only_contains_logged_in_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_credential("deepseek", "sk-deepseek-secret", model="deepseek-chat")
    monkeypatch.setattr(
        "agent.models._fetch_model_ids",
        lambda *_args: ["deepseek-reasoner", "deepseek-chat"],
    )

    catalog = discover_model_catalog("deepseek", "deepseek-chat")

    assert [item["key"] for item in catalog["providers"]] == ["deepseek"]
    assert catalog["providers"][0]["source"] == "live"
    assert catalog["providers"][0]["models"] == [
        "deepseek-chat",
        "deepseek-reasoner",
    ]
    assert "sk-deepseek-secret" not in json.dumps(catalog, ensure_ascii=False)


def test_live_discovery_keeps_saved_model_not_returned_by_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_credential("qwen", "sk-qwen-secret", model="private-model")
    monkeypatch.setattr("agent.models._fetch_model_ids", lambda *_args: ["qwen-plus"])

    models, error = discover_models(load_credentials()["qwen"])

    assert error == ""
    assert models == ["private-model", "qwen-plus"]


def test_openrouter_fallback_keeps_free_router(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_credential("openrouter", "sk-or-test-secret")
    monkeypatch.setattr(
        "agent.models._fetch_model_ids",
        lambda *_args: (_ for _ in ()).throw(TimeoutError("timed out")),
    )

    models, error = discover_models(load_credentials()["openrouter"])

    assert models == ["openrouter/free"]
    assert error == "模型列表请求超时"


@pytest.mark.parametrize(
    "failure",
    [
        HTTPError("https://api.example.com/v1/models", 401, "no", {}, None),
        TimeoutError("timed out"),
        ValueError("invalid response"),
    ],
)
def test_failed_discovery_uses_builtin_and_saved_models(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    save_credential("deepseek", "sk-deepseek-secret", model="private-model")

    def fail(*_args):
        raise failure

    monkeypatch.setattr("agent.models._fetch_model_ids", fail)
    models, error = discover_models(load_credentials()["deepseek"])

    assert error
    assert models == ["deepseek-chat", "deepseek-reasoner", "private-model"]


def test_custom_endpoint_failure_keeps_only_saved_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_credential(
        "custom",
        "sk-custom-secret",
        model="vendor-model",
        base_url="https://models.example.com/v1",
    )
    monkeypatch.setattr(
        "agent.models._fetch_model_ids",
        lambda *_args: (_ for _ in ()).throw(TimeoutError("timed out")),
    )

    models, error = discover_models(load_credentials()["custom"])

    assert models == ["vendor-model"]
    assert error == "模型列表请求超时"


def test_network_failures_are_distinguished_from_timeouts() -> None:
    assert _failure_message(URLError(TimeoutError("timed out"))) == "模型列表请求超时"
    assert _failure_message(URLError("connection refused")) == "无法连接模型端点"


def test_cross_provider_switch_updates_session_and_persists() -> None:
    save_credential("deepseek", "sk-deepseek-secret")
    save_credential("qwen", "sk-qwen-secret")
    store = SessionStore(".")
    store.active.configure(load_credentials()["deepseek"])

    provider, model = switch_model_provider(
        store.active,
        "qwen",
        "qwen3-coder-plus",
    )

    assert (provider, model) == ("qwen", "qwen3-coder-plus")
    assert store.active.provider == "qwen"
    assert store.active.model == "qwen3-coder-plus"
    assert store.active.api_key == "sk-qwen-secret"
    assert load_credentials()["qwen"].model == "qwen3-coder-plus"
    assert load_credentials()["deepseek"].model == "deepseek-chat"


def test_model_switch_rejects_missing_provider_and_empty_model() -> None:
    store = SessionStore(".")
    with pytest.raises(ValueError, match="/login"):
        switch_model(store.active, "model")
    save_credential("deepseek", "sk-deepseek-secret")
    store.active.configure(load_credentials()["deepseek"])
    with pytest.raises(ValueError, match="model is required"):
        switch_model(store.active, "  ")
    with pytest.raises(ValueError, match="not logged in"):
        switch_model_provider(store.active, "openai", "gpt-test")
