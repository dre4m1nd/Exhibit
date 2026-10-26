# -*- coding: utf-8 -*-
"""Tests for the filesystem and git tools."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agent.tools.fs import grep_files, list_dir, read_file
from agent.tools.git import git_branch_diff, git_diff, git_log, git_status

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


def test_fixture_repo_is_a_source_tree() -> None:
    assert (FIXTURE / "README.md").is_file()
    assert (FIXTURE / "src" / "core" / "report.py").is_file()
