# -*- coding: utf-8 -*-
"""Tests for the filesystem and git tools."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agent.tools.fs import grep_files, list_dir, read_file
from agent.tools.git import (
    git_branch_diff,
    git_diff,
    git_log,
    git_status,
    inspect_git_review_scope,
)

FIXTURE = Path(__file__).parent.parent / "examples" / "fixture-repo"


def test_list_dir_shows_src_tree() -> None:
    output = list_dir(str(FIXTURE))
    assert "src/" in output
    assert "README.md" in output


def test_list_dir_ignores_noise_directories(tmp_path: Path) -> None:
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "junk.js").write_text("x", encoding="utf-8")
    (tmp_path / "keep.py").write_text("x", encoding="utf-8")
    output = list_dir(str(tmp_path))
    assert "keep.py" in output
    assert "node_modules" not in output


def test_list_dir_reports_missing_path() -> None:
    assert "不存在" in list_dir("no-such-dir-anywhere")


def test_read_file_numbers_lines() -> None:
    output = read_file(str(FIXTURE / "README.md"))
    assert "1\t" in output
    assert "Fixture Repo" in output


def test_read_file_rejects_directories() -> None:
    assert "是目录" in read_file(str(FIXTURE))


def test_read_file_limit_caps_lines(tmp_path: Path) -> None:
    target = tmp_path / "many.py"
    target.write_text("\n".join(f"line {i}" for i in range(500)), encoding="utf-8")
    output = read_file(str(target), limit=10)
    assert "10\tline 9" in output
    assert "line 10" not in output


def test_grep_files_finds_matches() -> None:
    output = grep_files("Finding", str(FIXTURE))
    assert "report.py" in output
    assert "class Finding" in output


def test_grep_files_reports_no_match() -> None:
    assert "未找到匹配" in grep_files("zzz_nomatch_zzz", str(FIXTURE))


def test_grep_files_rejects_bad_regex() -> None:
    assert "正则表达式无效" in grep_files("[unclosed", str(FIXTURE))


def test_tools_refuse_paths_outside_the_repo(monkeypatch) -> None:
    monkeypatch.setenv("EXHIBIT_REPO_ROOT", str(FIXTURE))
    assert "越界" in read_file("C:\\Windows\\win.ini")
    assert "越界" in list_dir("..")


def test_tools_accept_paths_relative_to_repo(monkeypatch) -> None:
    monkeypatch.setenv("EXHIBIT_REPO_ROOT", str(FIXTURE))
    output = read_file("README.md")
    assert "Fixture Repo" in output


def test_tools_accept_caller_relative_path_under_repo_root(
    monkeypatch,
) -> None:
    monkeypatch.setenv("EXHIBIT_REPO_ROOT", str(FIXTURE.resolve()))
    monkeypatch.chdir(FIXTURE.parent.parent)

    listing = list_dir("examples/fixture-repo")
    body = read_file("examples/fixture-repo/README.md")

    assert "README.md" in listing
    assert str(FIXTURE.resolve()) in listing
    assert "Fixture Repo" in body


def test_git_tools_accept_caller_relative_path_under_repo_root(monkeypatch) -> None:
    monkeypatch.setenv("EXHIBIT_REPO_ROOT", str(FIXTURE.resolve()))
    monkeypatch.chdir(FIXTURE.parent.parent)

    status = git_status("examples/fixture-repo")
    diff = git_diff("examples/fixture-repo")

    assert isinstance(status, str)
    assert isinstance(diff, str)


def test_git_tools_read_the_fixture_repo(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "report.py").write_text("# TODO\n", encoding="utf-8")
    subprocess.run(["git", "add", "report.py"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=t@example.com",
         "commit", "-qm", "feat: initial fixture project"],
        cwd=tmp_path,
        check=True,
    )
    (tmp_path / "report.py").write_text("# TODO\nmore\n", encoding="utf-8")
    status = git_status(str(tmp_path))
    assert "report.py" in status

    log = git_log(str(tmp_path))
    assert "feat: initial fixture project" in log

    diff = git_diff(str(tmp_path))
    assert "TODO" in diff

    branch = git_branch_diff(str(tmp_path), base="HEAD")
    assert isinstance(branch, str)


def test_git_tools_handle_non_repo() -> None:
    # Use a temporary directory outside the parent repository.
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as outside:
        output = git_status(outside)
        assert "错误" in output


def _init_repo_with_commit(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    (path / "tracked.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=t@example.com",
            "commit",
            "-qm",
            "initial",
        ],
        cwd=path,
        check=True,
    )


def test_review_scope_reports_a_clean_worktree(tmp_path: Path) -> None:
    _init_repo_with_commit(tmp_path)

    scope = inspect_git_review_scope(str(tmp_path))

    assert scope.empty is True
    assert scope.untracked_only is False
    assert "未检测到工作区未提交改动" in scope.message


def test_review_scope_distinguishes_untracked_only(tmp_path: Path) -> None:
    _init_repo_with_commit(tmp_path)
    (tmp_path / "new.py").write_text("print('new')\n", encoding="utf-8")

    scope = inspect_git_review_scope(str(tmp_path))

    # Untracked-only changes are now reviewable, so the scope is not empty.
    assert scope.empty is False
    assert scope.untracked_only is True
    assert scope.files == ("new.py",)
    assert scope.untracked_files == ("new.py",)
    assert scope.reason == "untracked_only"
    assert "纳入审查" in scope.message


def test_git_diff_reveals_untracked_files(tmp_path: Path) -> None:
    _init_repo_with_commit(tmp_path)
    (tmp_path / "new.py").write_text("print('new')\n", encoding="utf-8")

    # `git_diff` intent-to-adds untracked files so their full content shows up.
    diff = git_diff(str(tmp_path))
    assert "new.py" in diff
    assert "+print('new')" in diff

    # The intent-to-add markers are cleaned up afterwards, so status is unchanged.
    porcelain = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "?? new.py" in porcelain

    scoped = inspect_git_review_scope(str(tmp_path))
    assert scoped.untracked_files == ("new.py",)


def test_review_scope_accepts_tracked_changes(tmp_path: Path) -> None:
    _init_repo_with_commit(tmp_path)
    (tmp_path / "tracked.txt").write_text("two\n", encoding="utf-8")

    scope = inspect_git_review_scope(str(tmp_path))

    assert scope.empty is False


def test_review_scope_reports_an_empty_commit_range(tmp_path: Path) -> None:
    _init_repo_with_commit(tmp_path)

    scope = inspect_git_review_scope(
        str(tmp_path),
        commit_range="HEAD..HEAD",
    )

    assert scope.empty is True
    assert "HEAD..HEAD" in scope.message


def test_fixture_repo_is_a_source_tree() -> None:
    assert (FIXTURE / "README.md").is_file()
    assert (FIXTURE / "src" / "core" / "report.py").is_file()


def test_git_tools_ignore_the_process_cwd_outside_the_review_root(tmp_path: Path) -> None:
    """A review must never report the agent's own repository state."""
    reviewed = tmp_path / "reviewed"
    elsewhere = tmp_path / "elsewhere"
    for repo, name in ((reviewed, "reviewed.txt"), (elsewhere, "elsewhere.txt")):
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        (repo / name).write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "add", name], cwd=repo, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Test", "-c", "user.email=t@example.com",
             "commit", "-qm", "init"],
            cwd=repo,
            check=True,
        )
    (reviewed / "changed.txt").write_text("y\n", encoding="utf-8")
    (elsewhere / "noise.txt").write_text("z\n", encoding="utf-8")

    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setenv("EXHIBIT_REPO_ROOT", str(reviewed))
        monkeypatch.chdir(elsewhere)
        status = git_status(".")
    finally:
        monkeypatch.undo()

    assert "changed.txt" in status
    assert "noise.txt" not in status
