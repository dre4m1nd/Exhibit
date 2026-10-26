# -*- coding: utf-8 -*-
"""Git tools for Exhibit: status, diff, log and branch comparison."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from agentscope.tool import FunctionTool

GIT_TIMEOUT = 60
MAX_DIFF_CHARS = 60000


def _run_git(args: list[str], repo_path: str) -> str:
    """Run a git command and return its stdout, or an error message."""
    requested = Path(repo_path).resolve()
    repo = requested
    configured = os.getenv("EXHIBIT_REPO_ROOT")
    sandbox = Path(configured).resolve() if configured else None
    if sandbox is not None and requested != sandbox:
        try:
            requested.relative_to(sandbox)
            repo = sandbox
        except ValueError:
            # The model may repeat a caller path relative to the process cwd.
            if (Path.cwd() / repo_path).resolve() == sandbox:
                repo = sandbox
    if not repo.exists():
        return f"错误：仓库路径不存在 {repo_path}"
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(repo),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT,
            check=False,
        )
    except FileNotFoundError:
        return "错误：找不到 git 可执行文件，请先安装 Git"
    except subprocess.TimeoutExpired:
        return f"错误：git {' '.join(args)} 执行超时"

    output = result.stdout.strip()
    if result.returncode != 0:
        detail = result.stderr.strip() or output or "未知错误"
        return f"错误：git {' '.join(args)} 失败：{detail}"
    if not output:
        return "（无输出）"
    return _truncate(output)


def _truncate(output: str) -> str:
    if len(output) <= MAX_DIFF_CHARS:
        return output
    return (
        output[:MAX_DIFF_CHARS]
        + f"\n\n（输出超过 {MAX_DIFF_CHARS} 字符，已截断；请改用更小的范围）"
    )


def git_status(repo_path: str = ".") -> str:
    """查看工作区状态：已暂存改动、未暂存改动与未跟踪文件。"""
    return _run_git(["status", "--short", "--branch"], repo_path)


def git_diff(repo_path: str = ".", target: str = "") -> str:
    """查看 diff。target 为空看工作区未提交改动；也接受文件路径、commit 或 `HEAD~2` 之类的引用。

    Args:
        repo_path: 仓库路径。
        target: 可选的 diff 目标，例如文件名、`--cached`、`HEAD~1`。
    """
    args = ["diff"]
    if target:
        args.extend(target.split())
    args.append("--stat")
    stat = _run_git(args, repo_path)
    detail = _run_git(args[:-1], repo_path)
    return f"{stat}\n\n{detail}"


def git_log(repo_path: str = ".", max_count: int = 10) -> str:
    """查看最近的提交历史（哈希、作者、日期、标题）。

    Args:
        repo_path: 仓库路径。
        max_count: 返回的提交数量，上限 50。
    """
    count = max(1, min(max_count, 50))
    return _run_git(
        [
            "log",
            f"--max-count={count}",
            "--date=short",
            "--pretty=format:%h %ad %an %s",
        ],
        repo_path,
    )


def git_branch_diff(repo_path: str = ".", base: str = "main", head: str = "") -> str:
    """对比两个分支的差异，用于审查某个分支相对基线的改动。

    Args:
        repo_path: 仓库路径。
        base: 基线分支或提交，默认 main。
        head: 目标分支或提交，默认为当前 HEAD。
    """
    target = f"{base}..{head}" if head else base
    stat = _run_git(["diff", "--stat", target], repo_path)
    detail = _run_git(["diff", target], repo_path)
    return f"{stat}\n\n{detail}"


def build_git_tools() -> list[FunctionTool]:
    """Build the git tools as AgentScope function tools."""
    return [
        FunctionTool(git_status, is_read_only=True),
        FunctionTool(git_diff, is_read_only=True),
        FunctionTool(git_log, is_read_only=True),
        FunctionTool(git_branch_diff, is_read_only=True),
    ]


__all__ = [
    "build_git_tools",
    "git_branch_diff",
    "git_diff",
    "git_log",
    "git_status",
]
