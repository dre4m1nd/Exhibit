# -*- coding: utf-8 -*-
"""Tests for mode-specific chat-agent tool registration."""

from __future__ import annotations

import asyncio
import io
import json

import pytest

from agentscope.event import TextBlockDeltaEvent
from agentscope.event import EventType, ReplyEndEvent
from agentscope.event._event import ReplyFinishedReason
from agentscope.message import Msg, TextBlock

from agent import app as app_module
from agent.agents import build_chat_agent
from agent.config import Config
from agent.permissions import FileEditor
from agent.protocol import Emitter


@pytest.fixture()
def config() -> Config:
    return Config(
        base_url="https://api.example.com/v1",
        api_key="test-key",
        model="test-model",
        max_iters=1,
        request_timeout=1,
    )


def _tool_names(agent) -> set[str]:
    return {tool.name for tool in agent.toolkit.tool_groups[0].tools}


class _FakeReviewAgent:
    def __init__(self, events, last_msg: Msg | None = None) -> None:
        self.events = events
        self.last_msg = last_msg

    async def reply_stream(self, *_args, **_kwargs):
        for event in self.events:
            yield event

    def _get_last_msg(self) -> Msg | None:
        return self.last_msg


def _delta(text: str) -> TextBlockDeltaEvent:
    return TextBlockDeltaEvent(
        reply_id="reply-1",
        block_id="block-1",
        delta=text,
    )


def _reply_end(finished_reason: str) -> ReplyEndEvent:
    return ReplyEndEvent(
        reply_id="reply-1",
        session_id="session-1",
        finished_reason=ReplyFinishedReason(finished_reason),
    )


def test_agent_mode_registers_edit_tools(config, tmp_path) -> None:
    agent = build_chat_agent(
        config,
        [],
        mode="agent",
        editor=FileEditor(tmp_path, approved=True),
    )

    assert {"write_file", "replace_in_file"} <= _tool_names(agent)


def test_plan_mode_does_not_register_edit_tools(config, tmp_path) -> None:
    agent = build_chat_agent(
        config,
        [],
        mode="plan",
        editor=FileEditor(tmp_path, approved=True),
    )

    assert not {"write_file", "replace_in_file"} & _tool_names(agent)


def test_collect_review_uses_streamed_text_when_final_message_is_empty() -> None:
    agent = _FakeReviewAgent([_delta("## 架构总览\n"), _delta("最终报告")])

    report = asyncio.run(
        app_module._collect_review(
            agent,
            "arch_overview",
            {"repo_path": "."},
            Emitter(io.StringIO()),
        )
    )

    assert report == "## 架构总览\n最终报告"


def test_collect_review_prefers_final_message_over_streamed_text() -> None:
    final = Msg(
        name="Exhibit",
        content=[TextBlock(type="text", text="最终报告")],
        role="assistant",
    )
    agent = _FakeReviewAgent([_delta("中间文本"), final])

    report = asyncio.run(
        app_module._collect_review(
            agent,
            "arch_overview",
            {"repo_path": "."},
            Emitter(io.StringIO()),
        )
    )

    assert report == "最终报告"


def test_run_chat_review_emits_the_report_to_the_tui(
    config: Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    final = Msg(
        name="Exhibit",
        content=[TextBlock(type="text", text="## 架构总览\n最终报告")],
        role="assistant",
    )
    agent = _FakeReviewAgent([_delta("## 架构总览\n"), final])
    monkeypatch.setattr(app_module, "build_agent", lambda *_args: agent)
    output = io.StringIO()

    report = asyncio.run(
        app_module._run_chat_review(
            "arch_overview",
            config,
            {"repo_path": "."},
            Emitter(output),
        )
    )

    events = [json.loads(line) for line in output.getvalue().splitlines()]
    assert report == "## 架构总览\n最终报告"
    assert events[-2] == {
        "type": "chat_delta",
        "text": "## 架构总览\n最终报告",
    }
    assert events[-1] == {
        "type": "chat_done",
        "text": "## 架构总览\n最终报告",
    }


def test_collect_review_appends_truncation_warning_on_unfinished_reply() -> None:
    agent = _FakeReviewAgent(
        [_delta("## 架构总览\n"), _delta("报告正文"), _reply_end("exceed_max_iters")]
    )

    report = asyncio.run(
        app_module._collect_review(
            agent,
            "arch_overview",
            {"repo_path": "."},
            Emitter(io.StringIO()),
        )
    )

    assert report.startswith("## 架构总览\n报告正文")
    # The truncated report carries a remediation note rather than ending cleanly.
    assert "EXHIBIT_MAX_OUTPUT_TOKENS" in report


def test_collect_review_skips_warning_when_reply_completed() -> None:
    agent = _FakeReviewAgent(
        [_delta("完整报告"), _reply_end("completed")]
    )

    report = asyncio.run(
        app_module._collect_review(
            agent,
            "arch_overview",
            {"repo_path": "."},
            Emitter(io.StringIO()),
        )
    )

    assert report == "完整报告"
    assert "EXHIBIT_MAX_OUTPUT_TOKENS" not in report
