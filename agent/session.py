# -*- coding: utf-8 -*-
"""In-process chat sessions, plan mode, permissions, and forking."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .credentials import SavedCredential, load_credentials, save_credential
from .providers import PROVIDERS, get_provider, validate_base_url

Mode = Literal["agent", "plan"]


@dataclass
class Session:
    """One conversation branch with isolated history and edit tracking."""

    session_id: str
    parent_id: str | None
    history: list[dict[str, str]] = field(default_factory=list)
    mode: Mode = "agent"
    read_files: list[str] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None

    @property
    def display_name(self) -> str:
        if self.parent_id:
            return f"{self.parent_id} → {self.session_id}"
        return self.session_id

    def add_message(self, role: str, content: str) -> None:
        self.history.append({"role": role, "content": content})

    def record_read(self, path: str) -> None:
        """Record a successful workspace read without duplicates."""
        if path not in self.read_files:
            self.read_files.append(path)

    def fork(self, child_id: str) -> "Session":
        """Create a child session without sharing mutable history."""
        return Session(
            session_id=child_id,
            parent_id=self.session_id,
            history=[dict(item) for item in self.history],
            mode=self.mode,
            read_files=list(self.read_files),
            changed_files=list(self.changed_files),
            provider=self.provider,
            model=self.model,
            base_url=self.base_url,
            api_key=self.api_key,
        )

    def configure(self, credential: SavedCredential) -> None:
        self.provider = credential.provider
        self.model = credential.model
        self.base_url = credential.base_url
        self.api_key = credential.api_key

    def clear_credential(self) -> None:
        """Forget the active credential after logout."""
        self.provider = None
        self.model = None
        self.base_url = None
        self.api_key = None


class SessionStore:
    """Track the active session and create sequential in-process forks."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self._project_context = ""
        self.main = Session(session_id="main", parent_id=None)
        self.active = self.main
        self.sessions: dict[str, Session] = {"main": self.main}
        self._fork_count = 0

    def fork(self) -> Session:
        self._fork_count += 1
        child_id = f"fork-{self._fork_count:02d}"
        child = self.active.fork(child_id)
        self.sessions[child_id] = child
        self.active = child
        return child

    def select(self, session_id: str) -> Session:
        if session_id not in self.sessions:
            choices = ", ".join(self.sessions)
            raise KeyError(f"unknown session '{session_id}', expected {choices}")
        self.active = self.sessions[session_id]
        return self.active

    def status(self) -> dict[str, object]:
        active = self.active
        return {
            "session": active.session_id,
            "parent": active.parent_id,
            "display_name": active.display_name,
            "provider": active.provider,
            "model": active.model,
            "mode": active.mode,
            "repo_path": str(self.root),
            "messages": len(active.history),
            "read_files": list(active.read_files),
            "changed_files": list(active.changed_files),
        }

    def remember_project_context(self, summary: str) -> None:
        """Keep the latest `/init` architecture summary for compacted chats."""
        self._project_context = summary.strip()

    def project_context(self) -> str:
        """Return the retained project context, if `/init` has run."""
        return self._project_context


def command_catalog(mode: Mode = "agent") -> list[dict[str, str]]:
    """Return slash commands with one-line descriptions for the TUI."""
    commands = [
        {"name": "/login", "description": "配置模型供应商与 API Key"},
        {"name": "/logout", "description": "删除当前供应商凭据"},
        {"name": "/provider", "description": "查看或切换模型供应商"},
        {"name": "/model", "description": "查看或切换模型"},
        {"name": "/status", "description": "查看当前会话状态"},
        {"name": "/init", "description": "生成架构总览与项目上下文"},
        {"name": "/clear", "description": "清空当前对话上下文"},
        {"name": "/compact", "description": "压缩当前对话上下文"},
        {"name": "/plan", "description": "进入或退出计划模式"},
        {"name": "/fork", "description": "从当前对话创建分支会话"},
        {"name": "/review", "description": "选择审查类型：arch、audit、repo 或 git"},
        {"name": "/diff", "description": "审查当前 Git 变更"},
        {"name": "/permissions", "description": "查看文件写入权限"},
        {"name": "/files", "description": "查看本轮读取或修改的文件"},
        {"name": "/undo", "description": "撤销最近一次可恢复的文件修改"},
        {"name": "/quit", "description": "退出 Exhibit"},
    ]
    if mode == "plan":
        blocked = {"/undo"}
        for item in commands:
            if item["name"] in blocked:
                item["enabled"] = "false"
    return commands


def toggle_plan(session: Session) -> Mode:
    session.mode = "plan" if session.mode == "agent" else "agent"
    return session.mode


def login(
    session: Session,
    provider: str,
    api_key: str,
    model: str = "",
    base_url: str = "",
    *,
    validate: bool = False,
) -> SavedCredential:
    known = get_provider(provider)
    endpoint_input = base_url.strip() or known.base_url
    if not endpoint_input:
        raise ValueError("base URL is required for a custom endpoint")
    endpoint = validate_base_url(endpoint_input, provider=known.key)
    selected_model = model.strip() or (known.models[0] if known.models else "")
    if not selected_model:
        raise ValueError("model is required for a custom endpoint")
    if validate:
        validate_api_key(endpoint, api_key, selected_model)
    credential = save_credential(
        provider,
        api_key,
        model=selected_model,
        base_url=endpoint,
    )
    session.configure(credential)
    return credential


def validate_api_key(base_url: str, api_key: str, model: str) -> None:
    """Perform a minimal OpenAI-compatible request without persisting secrets."""
    key = api_key.strip()
    if not key:
        raise ValueError("API key is required")
    request = Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(
            {
                "model": model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
                "stream": False,
            }
        ).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            if response.status >= 400:
                raise ValueError(f"credential check failed: HTTP {response.status}")
    except HTTPError as exc:
        if exc.code in {401, 403}:
            raise ValueError("API key was rejected by the provider") from exc
        raise ValueError(f"credential check failed: HTTP {exc.code}") from exc
    except URLError as exc:
        raise ValueError(f"credential check failed: {exc.reason}") from exc


def switch_provider(session: Session, provider: str) -> SavedCredential:
    known = get_provider(provider)
    saved = load_credentials().get(known.key)
    if saved is None:
        raise ValueError(f"provider '{known.key}' is not logged in; use /login")
    session.configure(saved)
    return saved


def ensure_provider(session: Session) -> str:
    """Load the sole saved provider when a fresh session has none selected."""
    if session.provider:
        return session.provider
    saved = load_credentials()
    if not saved:
        raise ValueError("no provider is logged in; use /login")
    if len(saved) > 1:
        raise ValueError("multiple providers are logged in; choose one with /provider")
    provider, credential = next(iter(saved.items()))
    session.configure(credential)
    return provider


def _known_models(provider_key: str, credential: SavedCredential) -> set[str]:
    """Model ids a provider is known to expose, used to disambiguate /model."""
    models = {credential.model} if credential.model else set()
    provider = PROVIDERS.get(provider_key)
    if provider is not None:
        models.update(provider.models)
    return models


def _model_provider(session: Session, model: str) -> str:
    """Return the logged-in provider that owns ``model``.

    `/model <id>` carries no provider, so a bare id is matched against each
    provider's known models instead of failing whenever more than one provider
    is logged in.
    """
    if session.provider:
        return session.provider
    saved = load_credentials()
    if not saved:
        raise ValueError("no provider is logged in; use /login")
    if len(saved) == 1:
        return next(iter(saved))
    matches = sorted(
        key for key, credential in saved.items() if model in _known_models(key, credential)
    )
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise ValueError(
            f"model '{model}' is offered by {', '.join(matches)}; "
            "pick one with /provider, then run /model again"
        )
    choices = ", ".join(sorted(saved))
    raise ValueError(
        f"model '{model}' is unknown to the logged-in providers ({choices}); "
        "pick a provider with /provider, then run /model again"
    )


def switch_model(session: Session, model: str) -> str:
    """Select and persist a model while keeping the active credential."""
    selected = model.strip()
    if not selected:
        raise ValueError("model is required")
    provider = _model_provider(session, selected)
    saved = load_credentials().get(provider)
    if saved is None:
        raise ValueError(f"provider '{provider}' is not logged in; use /login")
    save_credential(
        provider,
        saved.api_key,
        model=selected,
        base_url=saved.base_url,
    )
    # Keep provider, base_url and api_key consistent with the chosen model so
    # the next turn does not keep calling the previous provider.
    session.configure(
        SavedCredential(
            provider=provider,
            base_url=saved.base_url,
            model=selected,
            api_key=saved.api_key,
        )
    )
    return selected


def switch_model_provider(
    session: Session,
    provider: str,
    model: str,
) -> tuple[str, str]:
    """Switch provider and model together, then persist the selection."""
    key = provider.strip().lower()
    selected = model.strip()
    if not key:
        raise ValueError("provider is required")
    if not selected:
        raise ValueError("model is required")
    saved = load_credentials().get(key)
    if saved is None:
        raise ValueError(f"provider '{key}' is not logged in; use /login")
    save_credential(
        key,
        saved.api_key,
        model=selected,
        base_url=saved.base_url,
    )
    session.configure(
        SavedCredential(
            provider=key,
            base_url=saved.base_url,
            model=selected,
            api_key=saved.api_key,
        )
    )
    return key, selected


def provider_catalog() -> list[dict[str, object]]:
    saved = load_credentials()
    return [
        {
            "key": item.key,
            "label": item.label,
            "models": list(item.models),
            "logged_in": item.key in saved,
        }
        for item in PROVIDERS.values()
    ]


__all__ = [
    "Mode",
    "Session",
    "SessionStore",
    "command_catalog",
    "ensure_provider",
    "login",
    "provider_catalog",
    "switch_model",
    "switch_model_provider",
    "switch_provider",
    "toggle_plan",
    "validate_api_key",
]
