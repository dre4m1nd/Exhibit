# -*- coding: utf-8 -*-
"""Remember the last review per repository so a repeat run is incremental.

The cache lives in the user config dir, never inside the reviewed repo: reviews
must stay read-only. A snapshot of ``path -> (mtime, size)`` answers "what
changed since last time?" without hashing thousands of files.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from .credentials import config_dir
from .tools.fs import IGNORED_DIRS

MAX_SNAPSHOT_FILES = 20_000
MAX_LISTED_CHANGES = 20
# Beyond this share of changed files the old report is more noise than signal.
MAX_CHANGED_RATIO = 0.5


def _repo_path(repo: str | Path) -> Path:
    """Absolute repo path: the key must not depend on how the CLI spelled it."""
    return Path(repo).expanduser().resolve()


def _cache_file(repo: str | Path, task: str) -> Path:
    digest = hashlib.sha1(str(_repo_path(repo)).encode("utf-8")).hexdigest()[:16]
    return config_dir() / "cache" / f"{digest}-{task}.json"


def _snapshot(repo: str | Path) -> dict[str, list[int]]:
    """``relative path -> (mtime, size)``, pruning ignored and hidden dirs."""
    root = _repo_path(repo)
    if not root.is_dir():
        return {}
    files: dict[str, list[int]] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            name
            for name in dirnames
            if name not in IGNORED_DIRS and not name.startswith(".")
        ]
        for name in filenames:
            if len(files) >= MAX_SNAPSHOT_FILES:
                return files
            if name.endswith(".pyc"):
                continue
            path = Path(dirpath) / name
            try:
                stat = path.stat()
            except OSError:
                continue
            files[str(path.relative_to(root))] = [int(stat.st_mtime), stat.st_size]
    return files


def load(repo: str | Path, task: str) -> dict | None:
    """Return the previous review record, or None when there is none."""
    try:
        return json.loads(_cache_file(Path(repo), task).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save(repo: str | Path, task: str) -> None:
    """Store the file snapshot, ignoring write failures.

    Only the snapshot is kept: injecting the previous report cost ~2k tokens
    per run and measurably did not reduce exploration (69 -> 79 tool calls).
    """
    root = Path(repo)
    payload = {
        "when": time.strftime("%Y-%m-%d %H:%M"),
        "files": _snapshot(root),
    }
    path = _cache_file(root, task)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError:
        return


def preface(record: dict, repo: str | Path) -> str:
    """Prompt preface telling the model what is new since the last review."""
    previous: dict[str, list[int]] = record.get("files") or {}
    current = _snapshot(Path(repo))
    changed = sorted(
        name
        for name, stamp in current.items()
        if previous.get(name) != stamp
    )
    removed = sorted(set(previous) - set(current))
    if previous and len(changed) + len(removed) > MAX_CHANGED_RATIO * len(previous):
        return (
            f"上次审查（{record.get('when', '更早')}）之后改动过多，"
            "本次按全新审查处理，请忽略旧结论。\n\n"
        )

    listed = "、".join(changed[:MAX_LISTED_CHANGES]) or "无"
    lines = [
        f"上次审查：{record.get('when', '更早')}。",
        f"自那时起变更 {len(changed)} 个文件、删除 {len(removed)} 个：{listed}"
        + (" 等" if len(changed) > MAX_LISTED_CHANGES else "")
        + "。优先复核这些文件。",
        "",
    ]
    return "\n".join(lines)
