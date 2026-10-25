# -*- coding: utf-8 -*-
"""Load Exhibit prompts from Markdown files."""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

from .protocol import TASKS

_DEFAULT_PROMPT_DIR = Path(__file__).with_name("prompts")
_TASK_FILES = {
    "arch_overview": "arch_overview.md",
    "arch_audit": "arch_audit.md",
    "review_repo": "review_repo.md",
    "review_git": "review_git.md",
}
_PLACEHOLDER = re.compile(r"\{\{([a-z_]+)\}\}")


def prompt_dir() -> Path:
    """Return the active prompt directory, honoring EXHIBIT_PROMPT_DIR."""
    override = os.environ.get("EXHIBIT_PROMPT_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return _DEFAULT_PROMPT_DIR


@lru_cache(maxsize=None)
def _read_prompt_file(path: str) -> str:
    prompt_path = Path(path)
    try:
        return prompt_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"prompt file not found: {prompt_path}"
        ) from exc


def clear_prompt_cache() -> None:
    """Clear cached files after editing prompts in a long-running process."""
    _read_prompt_file.cache_clear()


def _read_prompt(filename: str) -> str:
    return _read_prompt_file(str(prompt_dir() / filename))


def _render(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    unresolved = _PLACEHOLDER.findall(rendered)
    if unresolved:
        names = ", ".join(sorted(set(unresolved)))
        raise ValueError(f"unresolved prompt placeholders: {names}")
    return rendered


def get_system_prompt(task: str) -> str:
    """Return a task prompt followed by the shared report requirements."""
    if task not in _TASK_FILES:
        raise KeyError(f"unknown task '{task}', expected one of {TASKS}")
    task_prompt = _read_prompt(_TASK_FILES[task])
    report_rules = _read_prompt("report_rules.md")
    return f"{task_prompt}\n\n{report_rules}"


def get_user_prompt(task: str, params: dict[str, str]) -> str:
    """Render the user prompt that kicks off the agent."""
    repo = params.get("repo_path") or "."
    scope_line = ""
    if task == "review_git":
        commit_range = params.get("commit_range")
        branch = params.get("branch")
        if commit_range:
            scope_line = f"审查范围：commit range `{commit_range}`\n"
        elif branch:
            scope_line = f"审查范围：分支 `{branch}` 相对于其基线的 diff\n"
        else:
            scope_line = "审查范围：工作区未提交的改动（git status + git diff）\n"
    return _render(
        _read_prompt("user_prompt.md"),
        {"repo_path": repo, "scope_line": scope_line},
    )
