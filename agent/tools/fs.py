# -*- coding: utf-8 -*-
"""Filesystem tools for Exhibit: listing, reading and searching files."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentscope.tool import FunctionTool

IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".idea",
    ".vscode",
}

MAX_FILE_BYTES = 256 * 1024
MAX_TREE_ENTRIES = 400
MAX_READ_LINES = 400
MAX_MATCHES = 200


@dataclass(frozen=True)
class Listing:
    """The result of listing a directory."""

    root: str
    entries: list[str]
    truncated: bool


def _resolve_inside(root: Path, path: str) -> Path:
    """Resolve ``path`` under ``root``, refusing to escape it."""
    candidate = Path(path)
    if not candidate.is_absolute():
        direct = (root / candidate).resolve()
        if direct.exists() and (direct == root or root in direct.parents):
            return direct
        # Models may echo a caller path that is relative to the process cwd
        # after EXHIBIT_REPO_ROOT has already narrowed the sandbox.
        from_cwd = (Path.cwd() / candidate).resolve()
        if from_cwd == root or root in from_cwd.parents:
            return from_cwd
        candidate = root / candidate
    resolved = candidate.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"路径越界（仅允许访问仓库内部）：{path}")
    return resolved


def _repo_root() -> Path:
    """The repository root that all tool paths are confined to.

    Defaults to the current working directory; ``EXHIBIT_REPO_ROOT`` overrides
    it so the TUI can point the tools at the repository under review.
    """
    configured = os.getenv("EXHIBIT_REPO_ROOT")
    return Path(configured).resolve() if configured else Path.cwd().resolve()


def _is_ignored(path: Path) -> bool:
    return any(part in IGNORED_DIRS for part in path.parts)


def list_dir(path: str = ".", max_depth: int = 3) -> str:
    """列出目录结构，自动忽略 .git、node_modules、.venv、__pycache__ 等噪音目录。

    Args:
        path: 仓库内的目录，相对仓库根目录或绝对路径。
        max_depth: 递归层数，默认 3 层，避免输出过大。
    """
    try:
        root = _resolve_inside(_repo_root(), path)
    except ValueError as exc:
        return f"错误：{exc}"
    if not root.exists():
        return f"错误：路径不存在 {path}"
    if root.is_file():
        return f"错误：{path} 是文件而非目录，请改用 read_file"

    entries: list[str] = []
    truncated = False

    def walk(current: Path, depth: int) -> None:
        nonlocal truncated
        if len(entries) >= MAX_TREE_ENTRIES:
            truncated = True
            return
        try:
            children = sorted(current.iterdir(), key=_sort_key)
        except (PermissionError, OSError):
            return
        for child in children:
            if len(entries) >= MAX_TREE_ENTRIES:
                truncated = True
                return
            if _is_ignored(child):
                continue
            is_dir = child.is_dir()
            indent = "  " * depth
            marker = "/" if is_dir else ""
            entries.append(f"{indent}{child.name}{marker}")
            if is_dir and depth < max_depth - 1:
                walk(child, depth + 1)

    walk(root, 0)
    body = "\n".join(entries) if entries else "（空目录）"
    footer = (
        f"\n\n（目录条目超过 {MAX_TREE_ENTRIES} 条，已截断；请缩小范围或指定子目录）"
        if truncated
        else ""
    )
    return f"目录 {root}：\n{body}{footer}"


def _sort_key(path: Path) -> tuple[int, str]:
    """Directories first, then case-insensitive name order."""
    return (0 if path.is_dir() else 1, path.name.lower())


def _looks_binary(path: Path) -> bool:
    """Detect binary files by NUL bytes in the first chunk."""
    try:
        with path.open("rb") as handle:
            return b"\x00" in handle.read(2048)
    except OSError:
        return True


def read_file(path: str, offset: int = 1, limit: int = 200) -> str:
    """读取文本文件内容，自动跳过二进制文件并限制行数。

    Args:
        path: 仓库内的文件路径，相对仓库根目录或绝对路径。
        offset: 起始行号，从 1 开始。
        limit: 最多返回的行数，上限 400。
    """
    try:
        target = _resolve_inside(_repo_root(), path)
    except ValueError as exc:
        return f"错误：{exc}"
    if not target.exists():
        return f"错误：文件不存在 {path}"
    if not target.is_file():
        return f"错误：{path} 是目录而非文件，请改用 list_dir"
    if _looks_binary(target):
        return f"跳过：{path} 是二进制文件"

    limit = max(1, min(limit, MAX_READ_LINES))
    offset = max(1, offset)
    try:
        size = target.stat().st_size
        with target.open("r", encoding="utf-8", errors="replace") as handle:
            if size > MAX_FILE_BYTES:
                handle.seek(0)
            lines: list[str] = []
            for index, line in enumerate(handle, start=1):
                if index < offset:
                    continue
                if len(lines) >= limit:
                    break
                lines.append(f"{index}\t{line.rstrip()}")
    except OSError as exc:
        return f"错误：读取失败 {path}: {exc}"

    if not lines:
        return f"（{path} 在 offset={offset} 之后没有内容）"
    header = f"文件 {target}"
    if size > MAX_FILE_BYTES:
        header += f"（文件 {size} 字节，仅展示前若干行，请配合 grep 使用）"
    return f"{header}：\n" + "\n".join(lines)


def grep_files(pattern: str, path: str = ".", head_limit: int = 50) -> str:
    """在仓库内用正则搜索文本，返回 `路径:行号: 内容` 列表。

    Args:
        pattern: Python 正则表达式。
        path: 搜索目录或单个文件，相对仓库根目录或绝对路径。
        head_limit: 最多返回的匹配条数，上限 200。
    """
    import re

    try:
        root = _resolve_inside(_repo_root(), path)
    except ValueError as exc:
        return f"错误：{exc}"
    if not root.exists():
        return f"错误：路径不存在 {path}"

    try:
        regex = re.compile(pattern)
    except re.error as exc:
        return f"错误：正则表达式无效 {pattern}: {exc}"

    head_limit = max(1, min(head_limit, MAX_MATCHES))
    matches: list[str] = []
    total = 0

    files = [root] if root.is_file() else _iter_files(root)
    for file_path in files:
        if _looks_binary(file_path):
            continue
        try:
            with file_path.open("r", encoding="utf-8", errors="replace") as fh:
                for line_no, line in enumerate(fh, start=1):
                    if regex.search(line):
                        total += 1
                        if len(matches) < head_limit:
                            matches.append(
                                f"{file_path}:{line_no}: {line.strip()}"
                            )
        except OSError:
            continue
        if total >= head_limit and len(matches) >= head_limit:
            break

    if not matches:
        return f"未找到匹配：{pattern}"
    footer = (
        f"\n\n（共 {total} 条匹配，仅显示前 {len(matches)} 条）"
        if total > len(matches)
        else ""
    )
    return "匹配结果：\n" + "\n".join(matches) + footer


def _iter_files(root: Path) -> Any:
    """Yield every non-ignored file under ``root``."""
    stack = [root]
    while stack:
        current = stack.pop()
        if _is_ignored(current):
            continue
        if current.is_file():
            yield current
            continue
        try:
            children = sorted(current.iterdir())
        except (PermissionError, OSError):
            continue
        stack.extend(children)


def build_fs_tools() -> list[FunctionTool]:
    """Build the filesystem tools as AgentScope function tools."""
    return [
        FunctionTool(list_dir, is_read_only=True),
        FunctionTool(read_file, is_read_only=True),
        FunctionTool(grep_files, is_read_only=True),
    ]


__all__ = [
    "IGNORED_DIRS",
    "Listing",
    "build_fs_tools",
    "grep_files",
    "list_dir",
    "read_file",
]
