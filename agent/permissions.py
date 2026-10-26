# -*- coding: utf-8 -*-
"""Workspace-scoped file edits with preview, confirmation, and undo."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

BLOCKED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    ".exhibit",
    "node_modules",
    "__pycache__",
}
BLOCKED_NAMES = {".env"}
MAX_WRITE_BYTES = 512 * 1024


@dataclass(frozen=True)
class EditPreview:
    """A pending file change that requires explicit user approval."""

    path: str
    action: str
    before: str
    after: str
    kind: Literal["file", "directory"] = "file"
    existed: bool = True

    def summary(self) -> str:
        if self.kind == "directory":
            return f"{self.action} {self.path}"
        return f"{self.action} {self.path}（{_line_delta(self.before, self.after)}）"


class FileEditor:
    """Perform approved edits inside one root directory."""

    def __init__(self, root: str | Path, *, approved: bool = False) -> None:
        self.root = Path(root).resolve()
        self.approved = approved
        self._undo: dict[str, list[EditPreview]] = {}
        self._pending: list[tuple[str, EditPreview]] = []
        self._trusted: set[str] = set()
        self._session_id = "main"

    @property
    def session_id(self) -> str:
        """The session that calls without an explicit id act on."""
        return self._session_id

    def preview_write(self, path: str, content: str) -> EditPreview:
        target = self._resolve(path)
        if target.exists() and target.is_dir():
            raise ValueError(f"target is a directory: {path}")
        before = _read_text(target) if target.exists() else ""
        if target.exists() and target.is_dir():
            raise ValueError(f"target is a directory: {path}")
        encoded = content.encode("utf-8")
        if len(encoded) > MAX_WRITE_BYTES:
            raise ValueError(f"content exceeds {MAX_WRITE_BYTES} bytes")
        action = "覆盖" if target.exists() else "新建"
        return EditPreview(
            str(target),
            action,
            before,
            content,
            kind="file",
            existed=target.exists(),
        )

    def preview_directory(self, path: str) -> EditPreview:
        """Preview creating one directory inside the workspace."""
        target = self._resolve(path)
        if target.exists():
            raise ValueError(f"target already exists: {path}")
        return EditPreview(
            str(target),
            "新建目录",
            "",
            "",
            kind="directory",
            existed=False,
        )

    def preview_replace(
        self,
        path: str,
        old: str,
        new: str,
        *,
        count: int = 1,
    ) -> EditPreview:
        target = self._resolve(path)
        if not target.is_file():
            raise ValueError(f"file does not exist: {path}")
        before = _read_text(target)
        occurrences = before.count(old)
        if occurrences == 0:
            raise ValueError("replacement text was not found")
        if count < 1:
            raise ValueError("count must be at least 1")
        after = before.replace(old, new, count)
        return EditPreview(
            str(target),
            "替换",
            before,
            after,
            kind="file",
            existed=True,
        )

    def apply(self, preview: EditPreview, session_id: str | None = None) -> None:
        if not self.approved:
            raise PermissionError("file writes require explicit approval")
        session_id = session_id or self._session_id
        self._apply_preview(preview)
        self._undo.setdefault(session_id, []).append(preview)

    def undo(self, session_id: str | None = None) -> EditPreview | None:
        # `/undo` is an explicit user action, so it does not require the
        # agent-write flag. Agent edits still go through approve_pending().
        session_id = session_id or self._session_id
        history = self._undo.get(session_id)
        if not history:
            return None
        preview = history[-1]
        target = Path(preview.path)
        if preview.kind == "directory":
            if not target.is_dir():
                raise ValueError("directory changed since the edit; refusing to undo")
            try:
                target.rmdir()
            except OSError as exc:
                raise ValueError("directory is not empty; refusing to undo") from exc
        elif not target.is_file() or _read_text(target) != preview.after:
            raise ValueError("file changed since the edit; refusing to undo")
        elif preview.existed:
            _write_text(target, preview.before)
        else:
            target.unlink()
        history.pop()
        return preview

    def can_undo(self, session_id: str | None = None) -> bool:
        return bool(self._undo.get(session_id or self._session_id))

    @property
    def has_pending(self) -> bool:
        return bool(self._pending)

    @property
    def pending(self) -> EditPreview | None:
        return self._pending[0][1] if self._pending else None

    def pending_preview(self, preview: EditPreview) -> dict[str, str]:
        """Return a protocol-safe preview without applying the edit."""
        if self.root not in Path(preview.path).resolve().parents:
            if Path(preview.path).resolve() != self.root:
                raise ValueError("preview is outside the workspace")
        return {
            "path": preview.path,
            "action": preview.action,
            "summary": preview.summary(),
            "before": preview.before,
            "after": preview.after,
        }

    def stage(self, preview: EditPreview, session_id: str | None = None) -> None:
        """Queue one preview for explicit confirmation by the TUI."""
        owner = session_id or self._session_id
        if owner in self._trusted:
            # The user already chose "allow for this session", so apply at once.
            self._apply_preview(preview)
            self._undo.setdefault(owner, []).append(preview)
            return
        self._pending.append((owner, preview))

    def trust_session(self, session_id: str | None = None) -> str:
        """Let later edits in this session skip the confirmation prompt."""
        owner = session_id or self._session_id
        self._trusted.add(owner)
        return owner

    def is_trusted(self, session_id: str | None = None) -> bool:
        return (session_id or self._session_id) in self._trusted

    def approve_pending(self, session_id: str | None = None) -> EditPreview | None:
        """Apply the staged preview after user approval."""
        session_id = session_id or self._session_id
        if not self._pending:
            return None
        owner, preview = self._pending[0]
        if owner != session_id:
            raise PermissionError("pending edit belongs to another session")
        self._pending.pop(0)
        if preview is not None:
            self._apply_preview(preview)
            self._undo.setdefault(session_id, []).append(preview)
        return preview

    def reject_pending(self, session_id: str | None = None) -> None:
        """Discard the staged preview without touching the filesystem."""
        session_id = session_id or self._session_id
        if not self._pending:
            return
        owner, _ = self._pending[0]
        if owner != session_id:
            raise PermissionError("pending edit belongs to another session")
        self._pending.pop(0)

    def fork_session(self, parent_id: str, child_id: str) -> None:
        """Copy undo history so child undo operations cannot affect the parent."""
        self._undo[child_id] = list(self._undo.get(parent_id, []))
        # A fork is a new branch, so it must earn its own write trust.
        self._trusted.discard(child_id)
        # Edits after the fork belong to the branch that is now active.
        self._session_id = child_id

    def _apply_preview(self, preview: EditPreview) -> None:
        target = Path(preview.path)
        if preview.kind == "directory":
            target.mkdir(parents=True, exist_ok=False)
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_text(target, preview.after)

    def _resolve(self, path: str) -> Path:
        candidate = Path(path)
        resolved = (
            candidate.resolve()
            if candidate.is_absolute()
            else (self.root / candidate).resolve()
        )
        if resolved != self.root and self.root not in resolved.parents:
            raise ValueError(f"path escapes workspace: {path}")
        relative = resolved.relative_to(self.root)
        if any(part in BLOCKED_DIRS for part in relative.parts):
            raise ValueError(f"path is protected: {path}")
        if resolved.name in BLOCKED_NAMES:
            raise ValueError(f"file is protected: {path}")
        return resolved


def _write_text(target: Path, text: str) -> None:
    """Write text verbatim so `newline` translation cannot desync an undo."""
    target.write_text(text, encoding="utf-8", newline="")


def _normalize(text: str) -> str:
    """Collapse line endings so a `\r\n` on-disk file matches an `\n` preview."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _line_delta(before: str, after: str) -> str:
    old = len(before.splitlines())
    new = len(after.splitlines())
    delta = new - old
    sign = f"{delta:+d}" if delta else "0"
    return f"{old} → {new} 行，{sign}"


def _read_text(path: Path) -> str:
    """Read UTF-8 text and reject binary files before any edit is staged."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"cannot read file: {path.name}") from exc
    if b"\x00" in raw[:2048]:
        raise ValueError(f"binary files are protected: {path.name}")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"only UTF-8 text files can be edited: {path.name}") from exc
    # Previews and writes are LF-only, so a CRLF file must be normalized here
    # or `undo()` would see a spurious "changed since the edit".
    return _normalize(text)


__all__ = ["EditPreview", "FileEditor", "MAX_WRITE_BYTES"]
