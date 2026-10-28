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
from agentscope.event import (
    ToolCallDeltaEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
    ToolResultEndEvent,
)
from agentscope.message import Msg, TextBlock
from agentscope.message._block import ToolResultState
from agentscope.permission import PermissionBehavior

from agent import app as app_module
from agent.agents import build_chat_agent
from agent.config import Config
from agent.credentials import SavedCredential
from agent.permissions import FileEditor
from agent.protocol import Emitter
from agent.session import SessionStore


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


def _tool(agent, name: str):
    return next(
        tool for tool in agent.toolkit.tool_groups[0].tools if tool.name == name
    )


def _permission(agent, name: str, tool_input: dict):
    return asyncio.run(
        agent._engine.check_permission(_tool(agent, name), tool_input)  # noqa: SLF001
    )


def test_agent_mode_allows_staged_edits_without_a_framework_prompt(
    config, tmp_path
) -> None:
    """AgentScope must not park edits before ``FileEditor`` can gate them."""
    agent = build_chat_agent(
        config,
        [],
        mode="agent",
        editor=FileEditor(tmp_path, approved=True),
    )

    decision = _permission(agent, "write_file", {"path": "a.txt", "content": "x"})

    assert decision.behavior == PermissionBehavior.ALLOW


def test_plan_mode_keeps_framework_permissions_untouched(config, tmp_path) -> None:
    agent = build_chat_agent(
        config,
        [],
        mode="plan",
        editor=FileEditor(tmp_path, approved=True),
    )

    assert agent.state.permission_context.allow_rules == {}


def test_stream_agent_resets_once_per_tool_call(config) -> None:
    """Per-delta resets flooded the protocol without any TUI handler."""
    events = [
        ToolCallStartEvent(
            reply_id="r", tool_call_id="c1", tool_call_name="list_dir"
        ),
        ToolCallDeltaEvent(reply_id="r", tool_call_id="c1", delta="{"),
        ToolCallDeltaEvent(reply_id="r", tool_call_id="c1", delta="}"),
        ToolCallEndEvent(reply_id="r", tool_call_id="c1"),
        ToolResultEndEvent(
            reply_id="r", tool_call_id="c1", state=ToolResultState.SUCCESS
        ),
        _delta("报告"),
    ]
    agent = _FakeReviewAgent(events)
    output = io.StringIO()

    asyncio.run(
        app_module._stream_agent(
            agent, "arch_overview", {"repo_path": "."}, Emitter(output)
        )
    )

    kinds = [json.loads(line)["type"] for line in output.getvalue().splitlines()]
    assert kinds.count("reset") == 1


def test_session_config_honours_env_provider(monkeypatch, tmp_path) -> None:
    saved = {
        "deepseek": SavedCredential(
            provider="deepseek",
            base_url="https://api.deepseek.com/v1",
            model="deepseek-chat",
            api_key="k1",
        ),
        "custom": SavedCredential(
            provider="custom",
            base_url="http://127.0.0.1:3425/v1",
            model="group/master",
            api_key="k2",
        ),
    }
    monkeypatch.setattr(app_module, "load_credentials", lambda: saved)
    monkeypatch.setenv("EXHIBIT_PROVIDER", "custom")
    store = SessionStore(tmp_path)

    config = app_module._session_config(store)

    assert config is not None
    assert config.base_url == "http://127.0.0.1:3425/v1"
    assert store.active.provider == "custom"


def test_login_hint_points_at_provider_when_several_are_saved(monkeypatch) -> None:
    monkeypatch.setattr(
        app_module, "load_credentials", lambda: {"a": None, "b": None}
    )

    assert "/provider" in app_module._login_hint()


def test_login_hint_points_at_login_without_saved_credentials(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "load_credentials", lambda: {})

    assert "/login" in app_module._login_hint()


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


def test_chat_once_rejects_an_empty_provider_reply() -> None:
    agent = _FakeReviewAgent([])

    with pytest.raises(ValueError, match="没有返回任何内容"):
        asyncio.run(
            app_module._chat_once(agent, "你好", Emitter(io.StringIO()))
        )
