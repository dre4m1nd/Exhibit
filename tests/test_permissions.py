# -*- coding: utf-8 -*-
"""Tests for the workspace-scoped file editor."""

from __future__ import annotations

import pytest

from agent.permissions import FileEditor


def test_unapproved_write_is_rejected(tmp_path) -> None:
    editor = FileEditor(tmp_path)
    preview = editor.preview_write("new.py", "print('ok')\n")

    with pytest.raises(PermissionError, match="approval"):
        editor.apply(preview)
    assert not (tmp_path / "new.py").exists()


def test_approved_write_and_undo_new_file(tmp_path) -> None:
    editor = FileEditor(tmp_path, approved=True)
    preview = editor.preview_write("src/new.py", "print('ok')\n")
    assert preview.action == "新建"

    editor.apply(preview)
    assert (tmp_path / "src" / "new.py").read_text("utf-8") == "print('ok')\n"

    undone = editor.undo()
    assert undone is preview
    assert not (tmp_path / "src" / "new.py").exists()


def test_replace_preview_and_restore_existing_file(tmp_path) -> None:
    target = tmp_path / "app.py"
    target.write_text("value = 1\n", encoding="utf-8")
    editor = FileEditor(tmp_path, approved=True)

    preview = editor.preview_replace("app.py", "1", "2")
    assert preview.action == "替换"
    assert preview.before == "value = 1\n"
    assert preview.after == "value = 2\n"

    editor.apply(preview)
    editor.undo()
    assert target.read_text("utf-8") == "value = 1\n"


@pytest.mark.parametrize("path", ["../outside.py", ".git/config", ".env", ".venv/x.py"])
def test_protected_or_out_of_workspace_paths_are_rejected(tmp_path, path: str) -> None:
    with pytest.raises(ValueError):
        FileEditor(tmp_path).preview_write(path, "x")


def test_missing_replacement_text_is_rejected(tmp_path) -> None:
    target = tmp_path / "app.py"
    target.write_text("hello\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not found"):
        FileEditor(tmp_path).preview_replace("app.py", "missing", "new")


def test_pending_preview_does_not_write_until_approved(tmp_path) -> None:
    editor = FileEditor(tmp_path)
    preview = editor.preview_write("pending.py", "print('pending')\n")
    editor.stage(preview)

    assert not (tmp_path / "pending.py").exists()
    assert editor.approve_pending() is preview
    assert (tmp_path / "pending.py").read_text("utf-8") == "print('pending')\n"


def test_rejected_preview_is_discarded(tmp_path) -> None:
    editor = FileEditor(tmp_path, approved=True)
    editor.stage(editor.preview_write("rejected.py", "x\n"))

    editor.reject_pending()

    assert editor.pending is None
    assert not (tmp_path / "rejected.py").exists()


def test_undo_is_allowed_for_explicit_user_action(tmp_path) -> None:
    editor = FileEditor(tmp_path)
    editor.stage(editor.preview_write("undo.py", "print('ok')\n"))
    editor.approve_pending()

    assert editor.undo() is not None
    assert not (tmp_path / "undo.py").exists()


def test_multiple_previews_are_confirmed_in_order(tmp_path) -> None:
    editor = FileEditor(tmp_path)
    editor.stage(editor.preview_write("first.py", "first\n"))
    editor.stage(editor.preview_write("second.py", "second\n"))

    assert editor.pending is not None
    assert editor.pending.path.endswith("first.py")
    editor.approve_pending()
    assert editor.pending is not None
    assert editor.pending.path.endswith("second.py")
    editor.reject_pending()

    assert (tmp_path / "first.py").exists()
    assert not (tmp_path / "second.py").exists()


def test_undo_refuses_to_overwrite_manual_changes(tmp_path) -> None:
    editor = FileEditor(tmp_path)
    editor.stage(editor.preview_write("app.py", "agent\n"))
    editor.approve_pending()
    (tmp_path / "app.py").write_text("manual\n", encoding="utf-8")

    with pytest.raises(ValueError, match="changed since"):
        editor.undo()
    assert (tmp_path / "app.py").read_text("utf-8") == "manual\n"


def test_directory_preview_is_approved_and_undone(tmp_path) -> None:
    editor = FileEditor(tmp_path)
    editor.stage(editor.preview_directory("src/new"))
    preview = editor.approve_pending()

    assert preview is not None
    assert (tmp_path / "src" / "new").is_dir()
    editor.undo()
    assert not (tmp_path / "src" / "new").exists()


def test_binary_and_non_utf8_files_are_protected(tmp_path) -> None:
    (tmp_path / "image.bin").write_bytes(b"\x89PNG\x00data")
    (tmp_path / "legacy.txt").write_bytes(b"\xff\xfe")
    editor = FileEditor(tmp_path)

    with pytest.raises(ValueError, match="binary"):
        editor.preview_write("image.bin", "x")
    with pytest.raises(ValueError, match="UTF-8"):
        editor.preview_write("legacy.txt", "x")


def test_forked_undo_histories_are_isolated(tmp_path) -> None:
    editor = FileEditor(tmp_path)
    editor.stage(editor.preview_write("main.py", "main\n"), "main")
    editor.approve_pending("main")
    editor.fork_session("main", "fork-01")

    editor.stage(editor.preview_write("child.py", "child\n"), "fork-01")
    editor.approve_pending("fork-01")

    assert editor.undo("fork-01").path.endswith("child.py")
    assert (tmp_path / "main.py").exists()

def test_crlf_files_can_be_undone(tmp_path) -> None:
    """A CRLF file must not look 'changed' just because Python wrote CRLF."""
    target = tmp_path / "app.py"
    target.write_bytes(b"value = 1\r\n")
    editor = FileEditor(tmp_path)

    editor.stage(editor.preview_replace("app.py", "1", "2"))
    editor.approve_pending()

    assert editor.undo() is not None
    assert target.read_bytes() == b"value = 1\n"


def test_session_trust_applies_later_writes_without_prompt(tmp_path) -> None:
    editor = FileEditor(tmp_path)
    editor.stage(editor.preview_write("first.py", "first\n"))
    editor.approve_pending()

    editor.trust_session("main")
    editor.stage(editor.preview_write("second.py", "second\n"))

    assert editor.pending is None
    assert (tmp_path / "second.py").read_text("utf-8") == "second\n"
    assert editor.is_trusted("main")


def test_fork_does_not_inherit_write_trust(tmp_path) -> None:
    editor = FileEditor(tmp_path)
    editor.trust_session("main")
    editor.fork_session("main", "fork-01")

    editor.stage(editor.preview_write("child.py", "child\n"), "fork-01")

    assert editor.pending is not None
    assert not editor.is_trusted("fork-01")
    assert not (tmp_path / "child.py").exists()
