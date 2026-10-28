# -*- coding: utf-8 -*-
"""Tests for slash-command dispatch in chat mode."""

from __future__ import annotations

import pytest
import io

from agent.chat import handle_command
from agent.config import Config
from agent.credentials import CONFIG_ENV, load_credentials, save_credential
from agent.permissions import FileEditor
from agent.protocol import Emitter
from agent.session import SessionStore


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(CONFIG_ENV, str(tmp_path / "config"))
    return tmp_path


def test_login_and_status_commands(isolated_env, monkeypatch) -> None:
    store = SessionStore(isolated_env)
    monkeypatch.setattr("agent.session.validate_api_key", lambda *_: None)

    result = handle_command(
        store,
        "/login",
        {"provider": "deepseek", "api_key": "sk-test-abcdefghij"},
    )
    assert result == {"provider": "deepseek", "model": "deepseek-chat"}
    status = handle_command(store, "/status", {})
    assert status["provider"] == "deepseek"
    assert status["mode"] == "agent"


def test_openrouter_login_is_validated_and_saved(
    isolated_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SessionStore(isolated_env)
    checked: list[tuple[str, str, str]] = []

    def validate(base_url: str, api_key: str, model: str) -> None:
        checked.append((base_url, api_key, model))

    monkeypatch.setattr("agent.session.validate_api_key", validate)
    result = handle_command(
        store,
        "/login",
        {"provider": "openrouter", "api_key": "sk-or-test-abcdefghij"},
    )

    assert result == {"provider": "openrouter", "model": "openrouter/free"}
    assert checked == [
        ("https://openrouter.ai/api/v1", "sk-or-test-abcdefghij", "openrouter/free")
    ]
    assert load_credentials()["openrouter"].model == "openrouter/free"


def test_failed_login_is_not_saved(isolated_env, monkeypatch) -> None:
    store = SessionStore(isolated_env)

    def reject(*_args) -> None:
        raise ValueError("API key was rejected by the provider")

    monkeypatch.setattr("agent.session.validate_api_key", reject)
    with pytest.raises(ValueError, match="rejected"):
        handle_command(
            store,
            "/login",
            {"provider": "openai", "api_key": "sk-secret-value"},
        )
    assert not (isolated_env / "credentials.json").exists()


def test_plan_mode_blocks_undo(isolated_env) -> None:
    store = SessionStore(isolated_env)
    handle_command(store, "/plan", {})

    with pytest.raises(PermissionError, match="read-only"):
        handle_command(store, "/undo", {}, FileEditor(isolated_env, approved=True))


def test_fork_returns_parent_and_child_ids(isolated_env) -> None:
    store = SessionStore(isolated_env)
    result = handle_command(store, "/fork", {})

    assert result["session"] == "fork-01"
    assert result["parent"] == "main"
    assert result["display_name"].endswith("fork-01")


def test_review_task_mapping(isolated_env, monkeypatch) -> None:
    import agent.app as app_module

    store = SessionStore(isolated_env)
    captured = {}

    monkeypatch.setattr(
        app_module,
        "_session_config",
        lambda _store: Config(
            base_url="https://api.example.com/v1",
            api_key="test-key",
            model="test-model",
            max_iters=1,
            request_timeout=1,
        ),
    )
    monkeypatch.setattr(
        app_module,
        "_run_chat_review",
        lambda task, *_args: captured.setdefault("task", task),
    )
    monkeypatch.setattr(app_module.asyncio, "run", lambda _awaitable: None)

    data = app_module._run_review_command(
        store,
        "/review",
        {"task": "audit"},
        Emitter(io.StringIO()),
    )

    assert captured["task"] == "arch_audit"
    assert data == {"task": "arch_audit", "shown_in_chat": True}


def test_review_accepts_multiple_tasks(isolated_env, monkeypatch) -> None:
    import agent.app as app_module

    store = SessionStore(isolated_env)
    captured: list[str] = []
    monkeypatch.setattr(
        app_module,
        "_session_config",
        lambda _store: Config(
            base_url="https://api.example.com/v1",
            api_key="test-key",
            model="test-model",
            max_iters=1,
            request_timeout=1,
        ),
    )
    monkeypatch.setattr(
        app_module,
        "_run_chat_review",
        lambda task, *_args: captured.append(task),
    )
    monkeypatch.setattr(app_module.asyncio, "run", lambda _awaitable: None)

    data = app_module._run_review_command(
        store,
        "/review",
        {"task": "audit,git"},
        Emitter(io.StringIO()),
    )

    assert captured == ["arch_audit", "review_git"]
    assert data == {"tasks": ["arch_audit", "review_git"], "shown_in_chat": True}


@pytest.mark.parametrize("value", ["REPO", " repo ", "repo,"])
def test_review_normalizes_task_names(
    isolated_env,
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    import agent.app as app_module

    store = SessionStore(isolated_env)
    captured: list[str] = []
    monkeypatch.setattr(
        app_module,
        "_session_config",
        lambda _store: Config(
            base_url="https://api.example.com/v1",
            api_key="test-key",
            model="test-model",
            max_iters=1,
            request_timeout=1,
        ),
    )
    monkeypatch.setattr(
        app_module,
        "_run_chat_review",
        lambda task, *_args: captured.append(task),
    )
    monkeypatch.setattr(app_module.asyncio, "run", lambda _awaitable: None)

    data = app_module._run_review_command(
        store,
        "/review",
        {"task": value},
        Emitter(io.StringIO()),
    )

    assert captured == ["review_repo"]
    assert data == {"task": "review_repo", "shown_in_chat": True}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("审查这个项目的架构", "arch_overview"),
        ("架构总览", "arch_overview"),
        ("架构审查", "arch_audit"),
        ("架构失职", "arch_audit"),
        ("审查这个项目", "review_repo"),
        ("代码审查", "review_repo"),
        ("未提交改动", "review_git"),
        ("分支差异", "review_git"),
    ],
)
def test_review_accepts_natural_language_task_names(
    isolated_env,
    monkeypatch: pytest.MonkeyPatch,
    value: str,
    expected: str,
) -> None:
    import agent.app as app_module

    store = SessionStore(isolated_env)
    captured: list[str] = []
    monkeypatch.setattr(
        app_module,
        "_session_config",
        lambda _store: Config(
            base_url="https://api.example.com/v1",
            api_key="test-key",
            model="test-model",
            max_iters=1,
            request_timeout=1,
        ),
    )
    monkeypatch.setattr(
        app_module,
        "_run_chat_review",
        lambda task, *_args: captured.append(task),
    )
    monkeypatch.setattr(app_module.asyncio, "run", lambda _awaitable: None)

    data = app_module._run_review_command(
        store,
        "/review",
        {"task": value},
        Emitter(io.StringIO()),
    )

    assert captured == [expected]
    assert data == {"task": expected, "shown_in_chat": True}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("审查 这个项目的 架构", "arch_overview"),
        ("审查 项目 架构", "arch_overview"),
        ("代码 审查", "review_repo"),
    ],
)
def test_review_accepts_space_separated_natural_language(
    isolated_env,
    monkeypatch: pytest.MonkeyPatch,
    value: str,
    expected: str,
) -> None:
    import agent.app as app_module

    store = SessionStore(isolated_env)
    captured: list[str] = []
    monkeypatch.setattr(
        app_module,
        "_session_config",
        lambda _store: Config(
            base_url="https://api.example.com/v1",
            api_key="test-key",
            model="test-model",
            max_iters=1,
            request_timeout=1,
        ),
    )
    monkeypatch.setattr(
        app_module,
        "_run_chat_review",
        lambda task, *_args: captured.append(task),
    )
    monkeypatch.setattr(app_module.asyncio, "run", lambda _awaitable: None)

    data = app_module._run_review_command(
        store,
        "/review",
        {"task": value},
        Emitter(io.StringIO()),
    )

    assert captured == [expected]
    assert data == {"task": expected, "shown_in_chat": True}


def test_review_rejects_unknown_task_with_clear_error(isolated_env) -> None:
    import agent.app as app_module

    store = SessionStore(isolated_env)

    with pytest.raises(ValueError, match="无法识别审查类型.*banana.*示例"):
        app_module._run_review_command(
            store,
            "/review",
            {"task": "banana"},
            Emitter(io.StringIO()),
        )


def test_review_without_task_defaults_to_repo(
    isolated_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import agent.app as app_module

    store = SessionStore(isolated_env)
    captured: list[str] = []
    monkeypatch.setattr(
        app_module,
        "_session_config",
        lambda _store: Config(
            base_url="https://api.example.com/v1",
            api_key="test-key",
            model="test-model",
            max_iters=1,
            request_timeout=1,
        ),
    )
    monkeypatch.setattr(
        app_module,
        "_run_chat_review",
        lambda task, *_args: captured.append(task),
    )
    monkeypatch.setattr(app_module.asyncio, "run", lambda _awaitable: None)

    data = app_module._run_review_command(
        store,
        "/review",
        {},
        Emitter(io.StringIO()),
    )

    assert captured == ["review_repo"]
    assert data == {"task": "review_repo", "shown_in_chat": True}


def test_unknown_command_is_rejected(isolated_env) -> None:
    store = SessionStore(isolated_env)
    with pytest.raises(ValueError, match="unknown command"):
        handle_command(store, "/no-such-command", {})


def test_undo_uses_editor_history(isolated_env) -> None:
    store = SessionStore(isolated_env)
    editor = FileEditor(isolated_env, approved=True)
    preview = editor.preview_write("created.py", "print('new')\n")
    editor.apply(preview)

    result = handle_command(store, "/undo", {}, editor)

    assert result["undone"].endswith("created.py")
    assert not (isolated_env / "created.py").exists()


def test_logout_clears_active_credential(isolated_env, monkeypatch) -> None:
    store = SessionStore(isolated_env)
    session = store.active
    session.provider = "openai"
    session.model = "gpt-test"
    session.base_url = "https://api.openai.com/v1"
    session.api_key = "secret"
    monkeypatch.setattr("agent.chat.remove_credential", lambda _: True)

    result = handle_command(store, "/logout", {"confirm": True})
    assert result == {"removed": True, "provider": "openai"}
    assert session.provider is None
    assert session.model is None
    assert session.base_url is None
    assert session.api_key is None


def test_logout_loads_the_only_saved_provider(
    isolated_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_credential("deepseek", "sk-test-abcdefghij")
    store = SessionStore(isolated_env)
    monkeypatch.setattr("agent.chat.remove_credential", lambda _: True)

    result = handle_command(store, "/logout", {"confirm": True})

    assert result == {"removed": True, "provider": "deepseek"}
    assert store.active.provider is None


def test_provider_switch_returns_new_model(isolated_env) -> None:
    save_credential("deepseek", "sk-test-abcdefghij")
    save_credential("qwen", "sk-test-abcdefghij", model="qwen3-coder-plus")
    store = SessionStore(isolated_env)
    store.active.configure(load_credentials()["deepseek"])

    result = handle_command(store, "/provider", {"provider": "qwen"})

    assert result == {"provider": "qwen", "model": "qwen3-coder-plus"}
    assert store.active.provider == "qwen"


def test_logout_of_another_provider_keeps_session_credential(
    isolated_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SessionStore(isolated_env)
    session = store.active
    session.provider = "openai"
    session.api_key = "secret"
    monkeypatch.setattr("agent.chat.remove_credential", lambda _: True)

    result = handle_command(
        store,
        "/logout",
        {"confirm": True, "provider": "deepseek"},
    )

    assert result == {"removed": True, "provider": "deepseek"}
    assert session.provider == "openai"
    assert session.api_key == "secret"


def test_undo_removes_path_from_changed_files(isolated_env) -> None:
    store = SessionStore(isolated_env)
    editor = FileEditor(isolated_env)
    editor.stage(editor.preview_write("created.py", "x\n"))
    editor.approve_pending(store.active.session_id)
    store.active.changed_files.append("created.py")

    handle_command(store, "/undo", {}, editor)

    assert store.active.changed_files == []


def test_files_separates_reads_and_changes(isolated_env) -> None:
    store = SessionStore(isolated_env)
    store.active.record_read("README.md")
    store.active.changed_files.append("app.py")

    assert handle_command(store, "/files", {}) == {
        "read_files": ["README.md"],
        "changed_files": ["app.py"],
    }


def test_quit_is_blocked_by_pending_edit(isolated_env) -> None:
    store = SessionStore(isolated_env)
    editor = FileEditor(isolated_env)
    editor.stage(editor.preview_write("pending.py", "x\n"))

    with pytest.raises(PermissionError, match="未确认"):
        handle_command(store, "/quit", {}, editor)


def test_logout_and_clear_require_confirmation(isolated_env) -> None:
    store = SessionStore(isolated_env)
    store.active.provider = "openai"
    store.active.add_message("user", "hello")

    with pytest.raises(ValueError, match="confirm"):
        handle_command(store, "/logout", {})
    with pytest.raises(ValueError, match="confirm"):
        handle_command(store, "/clear", {})

    assert store.active.provider == "openai"
    assert store.active.history
    assert handle_command(store, "/clear", {"confirm": True}) == {"cleared": True}


def test_fork_copies_undo_history_without_sharing(isolated_env) -> None:
    store = SessionStore(isolated_env)
    editor = FileEditor(isolated_env)
    editor.stage(editor.preview_write("main.py", "main\n"))
    editor.approve_pending("main")

    handle_command(store, "/fork", {}, editor)
    editor.stage(editor.preview_write("child.py", "child\n"))
    editor.approve_pending("fork-01")

    assert editor.undo("fork-01").path.endswith("child.py")
    assert (isolated_env / "main.py").exists()
    assert editor.undo("main").path.endswith("main.py")


def test_compact_retains_init_context(isolated_env) -> None:
    store = SessionStore(isolated_env)
    store.remember_project_context("# 架构总览\n入口是 app.py")
    store.active.add_message("user", "old")
    store.active.add_message("assistant", "recent")

    handle_command(store, "/compact", {})
    project = store.project_context()
    if project:
        store.active.add_message("system", project)

    contents = "\n".join(item["content"] for item in store.active.history)
    assert "# 架构总览" in contents
    assert "入口是 app.py" in contents


def test_model_without_arguments_returns_catalog(isolated_env, monkeypatch) -> None:
    store = SessionStore(isolated_env)
    save_credential("deepseek", "sk-test-abcdefghij")
    store.active.configure(load_credentials()["deepseek"])
    monkeypatch.setattr(
        "agent.chat.discover_model_catalog",
        lambda provider, model: {
            "kind": "model_catalog",
            "current": {"provider": provider, "model": model},
            "providers": [
                {
                    "key": provider,
                    "label": "DeepSeek",
                    "source": "fallback",
                    "error": "",
                    "models": [model],
                }
            ],
        },
    )

    result = handle_command(store, "/model", {})

    assert result["kind"] == "model_catalog"
    assert result["current"] == {
        "provider": "deepseek",
        "model": "deepseek-chat",
    }


def test_model_with_model_only_switches_current_provider(isolated_env) -> None:
    store = SessionStore(isolated_env)
    save_credential("deepseek", "sk-test-abcdefghij")

    result = handle_command(store, "/model", {"model": "deepseek-reasoner"})

    assert result == {
        "kind": "model_selected",
        "provider": "deepseek",
        "model": "deepseek-reasoner",
    }
    assert store.active.provider == "deepseek"
    assert store.active.model == "deepseek-reasoner"


def test_model_with_provider_and_model_switches_both(isolated_env) -> None:
    store = SessionStore(isolated_env)
    for provider in ("deepseek", "qwen"):
        save_credential(provider, "sk-test-abcdefghij")
    store.active.configure(load_credentials()["deepseek"])

    result = handle_command(
        store,
        "/model",
        {"provider": "qwen", "model": "qwen3-coder-plus"},
    )

    assert result == {
        "kind": "model_selected",
        "provider": "qwen",
        "model": "qwen3-coder-plus",
    }
    assert store.active.provider == "qwen"
    assert store.active.model == "qwen3-coder-plus"


def test_model_with_provider_requires_a_model(isolated_env) -> None:
    store = SessionStore(isolated_env)
    with pytest.raises(ValueError, match="model is required"):
        handle_command(store, "/model", {"provider": "qwen"})
