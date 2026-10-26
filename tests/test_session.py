# -*- coding: utf-8 -*-
"""Tests for command discovery, plan mode, and session forks."""

from __future__ import annotations

import pytest

from agent.credentials import CONFIG_ENV
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
    assert switch_provider(store.active, "deepseek").model == "deepseek-chat"


def test_provider_catalog_reports_login_state() -> None:
    login(SessionStore(".").active, "qwen", "sk-test-abcdefghij")

    catalog = provider_catalog()
    qwen = next(item for item in catalog if item["key"] == "qwen")
    assert qwen["logged_in"] is True
    assert qwen["models"] == ["qwen-plus", "qwen-coder-plus"]


def test_switching_to_unauthenticated_provider_is_rejected() -> None:
    store = SessionStore(".")
    with pytest.raises(ValueError, match="/login"):
        switch_provider(store.active, "openai")
