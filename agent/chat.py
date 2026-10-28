# -*- coding: utf-8 -*-
"""Command handling for Exhibit's persistent chat mode."""

from __future__ import annotations

from typing import Any
from pathlib import Path

from .credentials import load_credentials, remove_credential
from .models import discover_model_catalog
from .permissions import FileEditor
from .session import (
    SessionStore,
    command_catalog,
    ensure_provider,
    login,
    provider_catalog,
    switch_model,
    switch_model_provider,
    switch_provider,
    toggle_plan,
)

READ_ONLY = {"/status", "/permissions", "/files", "/provider", "/plan", "/fork"}


def handle_command(
    store: SessionStore,
    name: str,
    args: dict[str, Any],
    editor: Any = None,
) -> dict[str, Any]:
    """Execute a slash command and return a protocol-friendly result."""
    session = store.active
    normalized = name.strip().lower()

    if normalized == "/login":
        credential = login(
            session,
            str(args.get("provider", "openai")),
            str(args.get("api_key", "")),
            model=str(args.get("model", "")),
            base_url=str(args.get("base_url", "")),
            validate=True,
        )
        return {"provider": credential.provider, "model": credential.model}
    if normalized == "/logout":
        if not bool(args.get("confirm")):
            raise ValueError("logout requires confirm=true")
        target = str(args.get("provider") or ensure_provider(session))
        removed = remove_credential(target)
        # Only the active session's credential is cleared, so removing another
        # provider must not silently log this session out.
        if removed and target == session.provider:
            session.clear_credential()
        return {"removed": removed, "provider": target}
    if normalized == "/provider":
        requested = str(args.get("provider", "")).strip()
        if requested:
            credential = switch_provider(session, requested)
            return {"provider": credential.provider, "model": credential.model}
        return {"providers": provider_catalog()}
    if normalized == "/model":
        requested_provider = str(args.get("provider", "")).strip()
        requested = str(args.get("model", "")).strip()
        if requested_provider:
            if not requested:
                raise ValueError("model is required when switching provider")
            provider, model = switch_model_provider(
                session,
                requested_provider,
                requested,
            )
            return {"kind": "model_selected", "provider": provider, "model": model}
        if requested:
            selected = switch_model(session, requested)
            return {
                "kind": "model_selected",
                "provider": session.provider,
                "model": selected,
            }
        if session.provider is None:
            saved = load_credentials()
            if not saved:
                return {
                    "kind": "model_catalog",
                    "current": {"provider": "", "model": ""},
                    "providers": [],
                }
        return discover_model_catalog(session.provider, session.model)
    if normalized == "/status":
        return store.status()
    if normalized == "/plan":
        return {"mode": toggle_plan(session)}
    if normalized == "/fork":
        parent_id = session.session_id
        child = store.fork()
        if editor is not None:
            editor.fork_session(parent_id, child.session_id)
        return {
            "session": child.session_id,
            "parent": child.parent_id,
            "display_name": child.display_name,
            "mode": child.mode,
        }
    if normalized == "/clear":
        if not bool(args.get("confirm")):
            raise ValueError("clear requires confirm=true")
        session.history.clear()
        return {"cleared": True}
    if normalized == "/compact":
        keep = session.history[-2:]
        summary = (
            "已压缩上下文；保留目标、关键决策与文件变更："
            + (", ".join(session.changed_files) or "无")
        )
        session.history[:] = [{"role": "system", "content": summary}, *keep]
        return {"messages": len(keep), "changed_files": list(session.changed_files)}
    if normalized == "/permissions":
        return {
            "mode": session.mode,
            "writes": session.mode == "agent",
            "confirmation": "each_write",
        }
    if normalized == "/files":
        return {
            "read_files": list(session.read_files),
            "changed_files": list(session.changed_files),
        }
    if normalized == "/undo":
        if session.mode == "plan":
            raise PermissionError("plan mode is read-only")
        if editor is None:
            return {"undone": None}
        preview = editor.undo(session.session_id)
        if preview is not None:
            undone = _relative_to(editor.root, preview.path)
            if undone in session.changed_files:
                session.changed_files.remove(undone)
        return {"undone": preview.path if preview else None}
    if normalized == "/quit":
        if editor is not None and editor.has_pending:
            raise PermissionError("存在未确认的文件修改，请先允许或拒绝")
        return {"can_quit": True}
    if normalized == "/commands":
        return {"commands": command_catalog(session.mode)}

    raise ValueError(f"unknown command '{name}'")


def _relative_to(root: Path, path: str) -> str:
    """Return a workspace-relative POSIX path for session file tracking."""
    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return Path(path).name


__all__ = ["READ_ONLY", "handle_command"]
