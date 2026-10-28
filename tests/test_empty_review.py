# -*- coding: utf-8 -*-
"""Regression tests for empty review and diff results."""

from __future__ import annotations

import asyncio
import io

import pytest

from agent import app as app_module
from agent.config import Config
from agent.protocol import Emitter
from agent.session import SessionStore


class _EmptyReviewAgent:
    async def reply_stream(self, *_args, **_kwargs):
        if False:
            yield None

    def _get_last_msg(self):
        return None


@pytest.fixture()
def config() -> Config:
    return Config(
        base_url="https://api.example.com/v1",
        api_key="test-key",
        model="test-model",
        max_iters=1,
        request_timeout=1,
    )


def test_run_chat_review_rejects_an_empty_report(
    config: Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        app_module,
        "build_agent",
        lambda *_args: _EmptyReviewAgent(),
    )

    with pytest.raises(ValueError, match="没有生成报告内容"):
        asyncio.run(
            app_module._run_chat_review(
                "review_git",
                config,
                {"repo_path": "."},
                Emitter(io.StringIO()),
            )
        )


def test_clean_diff_returns_an_explicit_empty_result(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "tracked.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True)
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
        cwd=tmp_path,
        check=True,
    )
    store = SessionStore(tmp_path)
    output = io.StringIO()

    def fail_build(*_args):
        raise AssertionError("the model must not run for an empty diff")

    monkeypatch.setattr(app_module, "build_agent", fail_build)
    result = app_module._run_review_command(
        store,
        "/diff",
        {},
        Emitter(output),
    )

    assert result["empty"] is True
    assert "未检测到工作区未提交改动" in str(result["message"])
    assert "未检测到变更" in output.getvalue()
