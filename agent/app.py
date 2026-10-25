# -*- coding: utf-8 -*-
"""Exhibit's agent entrypoint.

Reads one JSON ``init`` line from stdin, runs the AgentScope agent while
streaming protocol events to stdout, and finishes with ``done``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from agentscope.agent import Agent
from agentscope.event import (
    EventType,
    TextBlockDeltaEvent,
    ThinkingBlockDeltaEvent,
    ToolCallDeltaEvent,
    TextBlockDeltaEvent,
    ThinkingBlockDeltaEvent,
    ToolCallEndEvent,
    ToolResultTextDeltaEvent,
)
from agentscope.message import Msg
from agentscope.message import TextBlock

from .agents import build_agent
from .config import load_config
from .prompt_loader import get_user_prompt
from .protocol import (
    MSG_INIT,
    Emitter,
    ProtocolError,
    TASKS,
    decode,
)


def _parse_args(fragment: str) -> dict:
    """Parse the accumulated JSON argument fragment of a tool call."""
    if not fragment:
        return {}
    try:
        parsed = json.loads(fragment)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _shorten(text: str, limit: int = 160) -> str:
    """Collapse a tool result into a single short line for the TUI."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[:limit] + " …"


async def _stream_agent(
    agent: Agent,
    task: str,
    params: dict,
    emitter: Emitter,
) -> None:
    """Run the agent and forward its events as protocol messages."""
    user_prompt = get_user_prompt(task, params)
    final_text: list[str] = []
    # tool_call_id -> [tool name, accumulated JSON argument fragment]
    calls: dict[str, list] = {}
    # tool_call_id -> accumulated tool result text
    results: dict[str, list[str]] = {}

    async for event in agent.reply_stream(
        Msg(
            name="user",
            content=[TextBlock(type="text", text=user_prompt)],
            role="user",
        ),
        yield_final_msg=True,
    ):
        event_type = getattr(event, "type", None)

        if isinstance(event, Msg):
            # The final assistant message is the authoritative report.
            text = (event.get_text_content() or "").strip()
            if text:
                final_text[:] = [text]
            continue

        if event_type == EventType.MODEL_CALL_START:
            emitter.status("thinking", "模型推理中")

        elif event_type == EventType.THINKING_BLOCK_DELTA:
            # Reasoning is intentionally not streamed into the report pane;
            # the status line already tells the user the model is thinking.
            pass

        elif event_type == EventType.TEXT_BLOCK_DELTA:
            if isinstance(event, TextBlockDeltaEvent) and event.delta:
                final_text.append(event.delta)
                emitter.token(event.delta)

        elif event_type == EventType.TOOL_CALL_START:
            name = getattr(event, "tool_call_name", "tool")
            calls[getattr(event, "tool_call_id", "")] = [name, ""]
            emitter.status("tool", f"调用 {name}")
            emitter.reset()

        elif event_type == EventType.TOOL_CALL_DELTA:
            # Tool arguments arrive as JSON fragments across delta events.
            if isinstance(event, ToolCallDeltaEvent):
                call_id = getattr(event, "tool_call_id", "")
                entry = calls.setdefault(call_id, ["", ""])
                entry[1] += event.delta

        elif event_type == EventType.TOOL_CALL_END:
            call_id = getattr(event, "tool_call_id", "")
            name, fragment = calls.get(call_id, ["", ""])
            emitter.tool_call(name, _parse_args(fragment))

        elif event_type == EventType.TOOL_RESULT_TEXT_DELTA:
            if isinstance(event, ToolResultTextDeltaEvent) and event.delta:
                call_id = getattr(event, "tool_call_id", "")
                results.setdefault(call_id, []).append(event.delta)

        elif event_type == EventType.TOOL_RESULT_END:
            call_id = getattr(event, "tool_call_id", "")
            name = calls.get(call_id, ["tool", ""])[0]
            emitter.tool_result(name, True, _shorten("".join(results.pop(call_id, []))))
            emitter.reset()

        elif event_type == EventType.REPLY_END:
            pass

    report = "".join(final_text).strip()
    if not report:
        # Fall back to the final assistant message in the context.
        last_msg = agent._get_last_msg()  # noqa: SLF001
        if last_msg is not None:
            report = (last_msg.get_text_content() or "").strip()
    if report:
        emitter.status("writing", "整理报告")
        emitter.report(report)
    else:
        emitter.error("模型没有产出报告内容，请调整参数后重试")


async def run(task: str, params: dict, emitter: Emitter) -> None:
    """Run one Exhibit task end to end."""
    repo_path = Path(params.get("repo_path") or ".").resolve()
    if not repo_path.exists():
        emitter.error(f"目标路径不存在：{repo_path}")
        return
    if not repo_path.is_dir():
        emitter.error(f"目标路径不是目录：{repo_path}")
        return
    # Confine the filesystem tools to the repository under review.
    os.environ["EXHIBIT_REPO_ROOT"] = str(repo_path)

    config = load_config()
    model = params.get("model") or None
    emitter.status("scanning", f"任务：{task}")
    agent = build_agent(task, config, model_name=model)
    await _stream_agent(agent, task, params, emitter)


def _read_init(stream) -> dict:
    """Block until a valid ``init`` message arrives on ``stream``."""
    while True:
        line = stream.readline()
        if not line:
            raise ProtocolError("stdin closed before init message")
        line = line.strip()
        if not line:
            continue
        try:
            message = decode(line)
        except ProtocolError:
            continue
        if message.get("type") == MSG_INIT:
            return message


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(prog="exhibit-agent")
    parser.add_argument(
        "--task",
        choices=TASKS,
        help="Run the task directly instead of reading an init line.",
    )
    parser.add_argument(
        "--repo-path",
        default=".",
        help="Target repository path.",
    )
    parser.add_argument(
        "--commit-range",
        default="",
        help="Commit range for the git review task.",
    )
    parser.add_argument(
        "--branch",
        default="",
        help="Branch for the git review task.",
    )
    parser.add_argument(
        "--model",
        default="",
        help="Model override.",
    )
    args = parser.parse_args(argv)

    emitter = Emitter()
    try:
        if args.task:
            task = args.task
            params = {
                "repo_path": args.repo_path,
                "commit_range": args.commit_range,
                "branch": args.branch,
                "model": args.model,
            }
        else:
            init = _read_init(sys.stdin)
            task = init.get("task")
            if task not in TASKS:
                raise ProtocolError(f"unknown task '{task}'")
            params = init.get("params") or {}

        asyncio.run(run(task, params, emitter))
    except Exception as exc:  # noqa: BLE001 - surface every failure to the TUI
        emitter.error(f"{type(exc).__name__}: {exc}")
    finally:
        emitter.done()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
