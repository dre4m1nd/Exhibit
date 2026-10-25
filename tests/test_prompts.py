# -*- coding: utf-8 -*-
"""Tests for file-based prompt loading."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from agent.prompt_loader import (
    clear_prompt_cache,
    get_system_prompt,
    get_user_prompt,
    prompt_dir,
)
from agent.protocol import TASKS

TMP_ROOT = Path(__file__).parent / ".tmp"


@pytest.fixture()
def prompt_copy() -> Path:
    """Copy prompts into a repository-local temporary directory."""
    import uuid

    target = TMP_ROOT / uuid.uuid4().hex
    shutil.copytree(prompt_dir(), target)
    clear_prompt_cache()
    try:
        yield target
    finally:
        clear_prompt_cache()
        shutil.rmtree(target, ignore_errors=True)


@pytest.mark.parametrize(
    ("task", "heading"),
    [
        ("arch_overview", "# 架构总览：<项目名>"),
        ("arch_audit", "# 架构失职审查：<项目名>"),
        ("review_repo", "# 整仓代码审查：<项目名>"),
        ("review_git", "# Git 变更审查：<项目名>"),
    ],
)
def test_system_prompt_loads_each_task(task: str, heading: str) -> None:
    prompt = get_system_prompt(task)
    assert heading in prompt
    assert "报告要求：" in prompt
    assert prompt.endswith("不要输出与报告无关的寒暄。")


def test_prompt_files_cover_all_tasks() -> None:
    assert set(TASKS) == {
        "arch_overview",
        "arch_audit",
        "review_repo",
        "review_git",
    }
    for task in TASKS:
        assert get_system_prompt(task)


def test_unknown_task_is_rejected() -> None:
    with pytest.raises(KeyError, match="unknown task"):
        get_system_prompt("not-a-task")


def test_user_prompt_defaults_to_working_tree() -> None:
    prompt = get_user_prompt("review_git", {"repo_path": "D:/repo"})
    assert prompt == (
        "目标仓库路径：D:/repo\n"
        "审查范围：工作区未提交的改动（git status + git diff）\n"
        "请开始分析，并在结束时给出完整的 Markdown 报告。"
    )


@pytest.mark.parametrize(
    ("params", "scope"),
    [
        ({"commit_range": "HEAD~2..HEAD"}, "commit range `HEAD~2..HEAD`"),
        ({"branch": "feature/review"}, "分支 `feature/review` 相对于其基线的 diff"),
    ],
)
def test_git_user_prompt_scope_variants(
    params: dict[str, str],
    scope: str,
) -> None:
    prompt = get_user_prompt("review_git", {"repo_path": ".", **params})
    assert f"审查范围：{scope}" in prompt


def test_non_git_task_has_no_scope_line() -> None:
    prompt = get_user_prompt(
        "arch_overview",
        {"repo_path": ".", "commit_range": "HEAD~1..HEAD"},
    )
    assert "审查范围：" not in prompt
    assert "请开始分析" in prompt


def test_prompt_directory_can_be_overridden(
    prompt_copy: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = prompt_copy / "arch_overview.md"
    target.write_text("# 自定义提示词", encoding="utf-8")
    monkeypatch.setenv("EXHIBIT_PROMPT_DIR", str(prompt_copy))

    prompt = get_system_prompt("arch_overview")
    assert prompt.startswith("# 自定义提示词\n\n报告要求：")


def test_missing_prompt_file_names_expected_path(
    prompt_copy: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (prompt_copy / "arch_audit.md").unlink()
    monkeypatch.setenv("EXHIBIT_PROMPT_DIR", str(prompt_copy))

    with pytest.raises(FileNotFoundError, match="arch_audit.md"):
        get_system_prompt("arch_audit")
