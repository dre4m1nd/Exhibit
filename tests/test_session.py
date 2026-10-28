# -*- coding: utf-8 -*-
"""Tests for command discovery, plan mode, and session forks."""

from __future__ import annotations

import pytest

from agent.credentials import CONFIG_ENV, save_credential
from agent.session import (
    SessionStore,
    command_catalog,
    login,
    provider_catalog,
    switch_model,
    switch_provider,
    toggle_plan,
)


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CONFIG_ENV, str(tmp_path))


def test_command_catalog_has_descriptions_and_no_help() -> None:
    commands = command_catalog()
    names = [item["name"] for item in commands]

    assert "/help" not in names
    assert "/plan" in names
    assert "/fork" in names
    assert all(item["description"] for item in commands)


def test_plan_mode_toggles_and_disables_undo() -> None:
    store = SessionStore(".")

    assert toggle_plan(store.active) == "plan"
    assert store.active.mode == "plan"
    undo = next(item for item in command_catalog("plan") if item["name"] == "/undo")
    assert undo["enabled"] == "false"
    assert toggle_plan(store.active) == "agent"


def test_fork_copies_history_without_sharing_it() -> None:
    store = SessionStore(".")
    store.active.add_message("user", "parent message")

    child = store.fork()
    child.add_message("user", "child message")
    child.mode = "plan"

    assert child.display_name == "main → fork-01"
    assert child.parent_id == "main"
    assert len(store.main.history) == 1
    assert len(child.history) == 2
    assert store.main.mode == "agent"
    assert store.active is child


def test_fork_has_independent_changed_files() -> None:
    store = SessionStore(".")
    store.active.changed_files.append("parent.py")

    child = store.fork()
    child.changed_files.append("child.py")

    assert store.main.changed_files == ["parent.py"]
    assert child.changed_files == ["parent.py", "child.py"]


def test_select_known_and_unknown_sessions() -> None:
    store = SessionStore(".")
    child = store.fork()

    assert store.select("main") is store.main
    assert store.select(child.session_id) is child
    with pytest.raises(KeyError, match="main"):
        store.select("missing")


def test_login_switches_provider_and_model() -> None:
    store = SessionStore(".")
    credential = login(store.active, "deepseek", "sk-test-abcdefghij")

    assert credential.model == "deepseek-chat"
    assert store.active.provider == "deepseek"
    assert switch_model(store.active, "deepseek-reasoner") == "deepseek-reasoner"
    assert switch_provider(store.active, "deepseek").model == "deepseek-reasoner"


def test_openrouter_login_uses_free_router() -> None:
    store = SessionStore(".")
    credential = login(store.active, "openrouter", "sk-or-test-abcdefghij")

    assert credential.base_url == "https://openrouter.ai/api/v1"
    assert credential.model == "openrouter/free"
    assert store.active.provider == "openrouter"


def test_custom_loopback_login_uses_supplied_model() -> None:
    store = SessionStore(".")
    credential = login(
        store.active,
        "custom",
        "magpie",
        model="group/master",
        base_url="http://127.0.0.1:3425/v1",
    )

    assert credential.base_url == "http://127.0.0.1:3425/v1"
    assert credential.model == "group/master"
    assert store.active.provider == "custom"


def test_switch_model_loads_the_only_saved_provider() -> None:
    login(SessionStore(".").active, "deepseek", "sk-test-abcdefghij")
    fresh = SessionStore(".").active

    assert switch_model(fresh, "deepseek-reasoner") == "deepseek-reasoner"
    assert fresh.provider == "deepseek"
    assert fresh.model == "deepseek-reasoner"


def test_switch_model_finds_the_owner_with_multiple_providers() -> None:
    login(SessionStore(".").active, "deepseek", "sk-test-abcdefghij")
    login(SessionStore(".").active, "qwen", "sk-test-abcdefghij")
    fresh = SessionStore(".").active

    assert switch_model(fresh, "deepseek-reasoner") == "deepseek-reasoner"
    assert fresh.provider == "deepseek"
    assert fresh.model == "deepseek-reasoner"


def test_provider_catalog_reports_login_state() -> None:
    login(SessionStore(".").active, "qwen", "sk-test-abcdefghij")

    catalog = provider_catalog()
    qwen = next(item for item in catalog if item["key"] == "qwen")
    assert qwen["logged_in"] is True
    assert qwen["models"] == ["qwen-plus", "qwen-coder-plus"]
    openrouter = next(item for item in catalog if item["key"] == "openrouter")
    assert openrouter["logged_in"] is False
    assert openrouter["models"] == ["openrouter/free"]


def test_switching_to_unauthenticated_provider_is_rejected() -> None:
    store = SessionStore(".")
    with pytest.raises(ValueError, match="/login"):
        switch_provider(store.active, "openai")


def test_switch_model_resolves_a_bare_model_id_to_its_provider() -> None:
    save_credential(
        "deepseek",
        "k1",
        model="deepseek-chat",
        base_url="https://api.deepseek.com/v1",
    )
    save_credential(
        "custom",
        "k2",
        model="group/master",
        base_url="http://127.0.0.1:3425/v1",
    )
    session = SessionStore(".").active

    assert switch_model(session, "group/master") == "group/master"
    assert session.provider == "custom"
    assert session.base_url == "http://127.0.0.1:3425/v1"
    assert session.api_key == "k2"


def test_switch_model_matches_a_builtin_model_to_its_provider() -> None:
    save_credential(
        "deepseek",
        "k1",
        model="deepseek-chat",
        base_url="https://api.deepseek.com/v1",
    )
    save_credential(
        "custom",
        "k2",
        model="group/master",
        base_url="http://127.0.0.1:3425/v1",
    )
    session = SessionStore(".").active

    assert switch_model(session, "deepseek-chat") == "deepseek-chat"
    assert session.provider == "deepseek"


def test_switch_model_reports_an_unknown_id_with_several_providers() -> None:
    save_credential(
        "deepseek",
        "k1",
        model="deepseek-chat",
        base_url="https://api.deepseek.com/v1",
    )
    save_credential(
        "custom",
        "k2",
        model="group/master",
        base_url="http://127.0.0.1:3425/v1",
    )
    session = SessionStore(".").active

    with pytest.raises(ValueError, match="unknown to the logged-in providers"):
        switch_model(session, "no-such-model")
