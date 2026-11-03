# -*- coding: utf-8 -*-
"""Tests for the per-repository review cache (incremental second pass)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent import review_cache
from agent.credentials import CONFIG_ENV


@pytest.fixture(autouse=True)
def isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config = tmp_path / "config"
    monkeypatch.setenv(CONFIG_ENV, str(config))
    repo = tmp_path / "repo"
    repo.mkdir()
    for name in ("app.py", "db.py", "api.py", "job.py"):
        (repo / name).write_text("x\n", encoding="utf-8")
    return repo


def test_save_then_load_round_trips_the_report(isolated_config: Path) -> None:
    review_cache.save(isolated_config, "arch_overview", "# 报告\n内容")

    record = review_cache.load(isolated_config, "arch_overview")

    assert record is not None
    assert record["report"].startswith("# 报告")
    assert "app.py" in record["files"]


def test_empty_report_is_not_cached(isolated_config: Path) -> None:
    review_cache.save(isolated_config, "arch_overview", "   ")

    assert review_cache.load(isolated_config, "arch_overview") is None


def test_preface_names_the_changed_files(isolated_config: Path) -> None:
    review_cache.save(isolated_config, "arch_overview", "# 旧报告")
    record = review_cache.load(isolated_config, "arch_overview")
    (isolated_config / "app.py").write_text("changed\n", encoding="utf-8")

    text = review_cache.preface(record, isolated_config)

    assert "变更 1 个文件" in text
    assert "app.py" in text
    assert "# 旧报告" in text


def test_preface_falls_back_to_a_full_review_when_everything_changed(
    isolated_config: Path,
) -> None:
    review_cache.save(isolated_config, "arch_overview", "# 旧报告")
    record = review_cache.load(isolated_config, "arch_overview")
    (isolated_config / "app.py").write_text("changed\n", encoding="utf-8")
    (isolated_config / "db.py").write_text("changed\n", encoding="utf-8")
    (isolated_config / "api.py").write_text("changed\n", encoding="utf-8")
    (isolated_config / "new.py").write_text("x\n", encoding="utf-8")

    text = review_cache.preface(record, isolated_config)

    assert "按全新审查处理" in text
    assert "# 旧报告" not in text


def test_cache_lives_outside_the_reviewed_repo(isolated_config: Path) -> None:
    review_cache.save(isolated_config, "arch_overview", "# 报告")

    assert not any(p.name == "cache" for p in isolated_config.iterdir())
