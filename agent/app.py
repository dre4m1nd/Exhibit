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
    ToolResultTextDeltaEvent,
)
from agentscope.message import Msg
from agentscope.message import TextBlock

from .agents import build_agent, build_chat_agent
from .chat import handle_command
from .config import Config, load_config
from .credentials import load_credentials
from .permissions import FileEditor
from .prompt_loader import get_user_prompt
from .protocol import (
    MSG_INIT,
    MSG_CHAT,
    MSG_COMMAND,
    MSG_PERMISSION_RESPONSE,
    Emitter,
    ProtocolError,
    TASKS,
    decode,
)
from .session import SessionStore
from .tools.git import GitReviewScope, inspect_git_review_scope


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


def _tool_result_ok(event: object) -> bool:
    """Return whether a ToolResultEndEvent represents a successful call."""
    state = getattr(event, "state", "success")
    value = getattr(state, "value", state)
    return str(value).lower() == "success"


def _forward_tool_event(
    event: object,
    emitter: Emitter,
    calls: dict[str, list],
    results: dict[str, list[str]],
) -> None:
    """Translate AgentScope tool events into TUI call/result records."""
    event_type = getattr(event, "type", None)
    if event_type == EventType.TOOL_CALL_START:
        name = getattr(event, "tool_call_name", "tool")
        calls[getattr(event, "tool_call_id", "")] = [name, ""]
        emitter.status("tool", f"调用 {name}")
    elif event_type == EventType.TOOL_CALL_DELTA:
        if isinstance(event, ToolCallDeltaEvent):
            call_id = getattr(event, "tool_call_id", "")
            entry = calls.setdefault(call_id, ["", ""])
            entry[1] += event.delta
    elif event_type == EventType.TOOL_CALL_END:
        call_id = getattr(event, "tool_call_id", "")
        name, fragment = calls.get(call_id, ["tool", ""])
        emitter.tool_call(name or "tool", _parse_args(fragment))
    elif event_type == EventType.TOOL_RESULT_TEXT_DELTA:
        if isinstance(event, ToolResultTextDeltaEvent) and event.delta:
            call_id = getattr(event, "tool_call_id", "")
            results.setdefault(call_id, []).append(event.delta)
    elif event_type == EventType.TOOL_RESULT_END:
        call_id = getattr(event, "tool_call_id", "")
        name = calls.get(call_id, ["tool", ""])[0] or "tool"
        emitter.tool_result(
            name,
            _tool_result_ok(event),
            _shorten("".join(results.pop(call_id, []))),
        )


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
            if isinstance(event, ThinkingBlockDeltaEvent) and event.delta:
                emitter.think_delta(event.delta)

        elif event_type == EventType.TEXT_BLOCK_DELTA:
            if isinstance(event, TextBlockDeltaEvent) and event.delta:
                final_text.append(event.delta)
                emitter.token(event.delta)
        elif event_type in {
            EventType.TOOL_CALL_START,
            EventType.TOOL_CALL_DELTA,
            EventType.TOOL_CALL_END,
            EventType.TOOL_RESULT_TEXT_DELTA,
            EventType.TOOL_RESULT_END,
        }:
            _forward_tool_event(event, emitter, calls, results)
            if event_type == EventType.TOOL_CALL_START:
                # Discard the draft only once the model stops talking and acts.
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


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser shared by headless runs and tests."""
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
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    args = _build_parser().parse_args(argv)

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
            _chat_loop(Path(args.repo_path).resolve(), emitter)
            return 0
        asyncio.run(run(task, params, emitter))
    except Exception as exc:  # noqa: BLE001 - surface every failure to the TUI
        emitter.error(f"{type(exc).__name__}: {exc}")
    finally:
        emitter.done()
    return 0


def _chat_loop(repo_path: Path, emitter: Emitter) -> None:
    """Read chat and command messages until stdin closes."""
    store = SessionStore(repo_path)
    editor = FileEditor(repo_path)
    os.environ["EXHIBIT_REPO_ROOT"] = str(repo_path)
    emitter.session(store.status())
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        try:
            message = decode(line.strip())
        except ProtocolError:
            continue
        message_type = message.get("type")
        if message_type == MSG_CHAT:
            text = str(message.get("text", ""))
            store.active.add_message("user", text)
            try:
                config = _session_config(store)
                if config is None:
                    emitter.chat_done(_login_hint())
                    continue
                agent = build_chat_agent(
                    config,
                    store.active.history,
                    mode=store.active.mode,
                    editor=editor,
                    session=store.active,
                )
                reply = asyncio.run(_chat_once(agent, text, emitter))
                if reply:
                    store.active.add_message("assistant", reply)
                emitter.chat_done(reply)
                if editor.pending is not None:
                    preview = editor.pending
                    emitter.permission_request(
                        f"edit-{len(store.active.changed_files) + 1}",
                        preview.path,
                        preview.action,
                        preview.summary(),
                        session_id=store.active.session_id,
                        trusted=editor.is_trusted(store.active.session_id),
                    )
            except Exception as exc:  # noqa: BLE001 - show model failures in TUI
                emitter.error(f"{type(exc).__name__}: {exc}")
        elif message_type == MSG_COMMAND:
            name = str(message.get("name", ""))
            try:
                args = message.get("args") or {}
                if name in {"/init", "/review", "/diff"}:
                    data = _run_review_command(store, name, args, emitter)
                else:
                    data = handle_command(store, name, args, editor)
                    if name == "/compact":
                        project = store.project_context()
                        if project:
                            store.active.add_message("system", project)
                emitter.command_result(name, data)
                emitter.session(store.status())
            except Exception as exc:  # noqa: BLE001 - show command errors in the TUI
                emitter.error(str(exc))
        elif message_type == MSG_PERMISSION_RESPONSE:
            approved = bool(message.get("approved"))
            if editor.pending is None:
                emitter.error("没有等待处理中的文件修改")
                continue
            session_id = store.active.session_id
            if not approved:
                scope = str(message.get("scope", "once"))
                if scope == "session":
                    editor.trust_session(session_id)
                    store.active.add_message("system", "已允许本会话后续文件写入。")
                else:
                    store.active.add_message("system", "用户拒绝了文件修改。")
                editor.reject_pending(session_id)
                emitter.chat_done(
                    "已允许本会话后续写入。"
                    if scope == "session"
                    else "已拒绝文件修改。"
                )
                if editor.pending is not None:
                    preview = editor.pending
                    emitter.permission_request(
                        f"edit-{len(store.active.changed_files) + 1}",
                        preview.path,
                        preview.action,
                        preview.summary(),
                        session_id=session_id,
                    )
                continue
            preview = editor.approve_pending(session_id)
            if preview is not None:
                relative = Path(preview.path).resolve().relative_to(editor.root)
                name = str(relative).replace("\\", "/")
                if name not in store.active.changed_files:
                    store.active.changed_files.append(name)
                store.active.add_message("system", f"已应用文件修改：{name}")
                emitter.chat_done(f"已应用修改：{name}")
                if editor.pending is not None:
                    next_preview = editor.pending
                    emitter.permission_request(
                        f"edit-{len(store.active.changed_files) + 1}",
                        next_preview.path,
                        next_preview.action,
                        next_preview.summary(),
                        session_id=session_id,
                        trusted=editor.is_trusted(session_id),
                    )


_REVIEW_ALIASES = {
    "arch": "arch",
    "architecture": "arch",
    "architecture overview": "arch",
    "overview": "arch",
    "arch_overview": "arch",
    "架构": "arch",
    "架构总览": "arch",
    "项目架构": "arch",
    "审查这个项目的架构": "arch",
    "审查项目架构": "arch",
    "audit": "audit",
    "architecture audit": "audit",
    "arch_audit": "audit",
    "架构审查": "audit",
    "架构失职": "audit",
    "架构缺陷": "audit",
    "架构问题": "audit",
    "repo": "repo",
    "code": "repo",
    "code review": "repo",
    "review_repo": "repo",
    "整仓": "repo",
    "整仓审查": "repo",
    "代码审查": "repo",
    "项目审查": "repo",
    "审查项目": "repo",
    "审查这个项目": "repo",
    "git": "git",
    "diff": "git",
    "review_git": "git",
    "变更": "git",
    "变更审查": "git",
    "git审查": "git",
    "git 审查": "git",
    "未提交改动": "git",
    "未提交变更": "git",
    "分支差异": "git",
    "提交范围": "git",
    "commit range": "git",
}


def _parse_review_tasks(value: str) -> list[str]:
    """Normalize explicit task names and common natural-language requests."""
    parts = [
        part.strip()
        for part in value.replace("，", ",").split(",")
        if part.strip()
    ]
    if not parts:
        return ["repo"]

    tasks: list[str] = []
    for part in parts:
        key = " ".join(part.lower().split())
        task = _REVIEW_ALIASES.get(key) or _review_task_from_phrase(key)
        if task is None:
            raise ValueError(
                f"无法识别审查类型：{part}；"
                "可选 arch（架构总览）、audit（架构审查）、"
                "repo（整仓审查）、git（Git 变更）。"
                "示例：/review arch"
            )
        if task not in tasks:
            tasks.append(task)
    return tasks


def _review_task_from_phrase(phrase: str) -> str | None:
    """Infer a review mode from a short natural-language description."""
    normalized = "".join(phrase.split())
    if "架构" in normalized:
        audit_terms = ("失职", "缺陷", "问题", "风险", "越层", "循环依赖", "职责")
        return (
            "audit"
            if any(term in normalized for term in audit_terms)
            else "arch"
        )
    if any(
        term in normalized for term in ("git", "diff", "变更", "提交", "commit")
    ):
        return "git"
    if any(
        term in normalized
        for term in ("代码", "整仓", "仓库", "项目", "repo", "code", "project")
    ):
        return "repo"
    return None


def _run_review_command(
    store: SessionStore,
    name: str,
    args: dict,
    emitter: Emitter,
) -> dict[str, object]:
    """Run the existing review flow and keep its report in chat history."""
    scope = "只读审查" if store.active.mode == "plan" and name != "/init" else "审查"
    review_tasks = {
        "arch": "arch_overview",
        "audit": "arch_audit",
        "repo": "review_repo",
        "git": "review_git",
    }
    requested = _parse_review_tasks(str(args.get("task", "repo")))
    if name == "/review" and len(requested) > 1:
        for task in [review_tasks[item] for item in requested]:
            _run_one_review(store, task, args, emitter, scope)
        return {
            "tasks": [review_tasks[item] for item in requested],
            "shown_in_chat": True,
        }
    task = (
        review_tasks[requested[0]]
        if name == "/review"
        else "arch_overview" if name == "/init" else "review_git"
    )
    if name == "/init":
        store.active.add_message("user", "/init：生成架构总览与项目上下文")
    outcome = _run_one_review(store, task, args, emitter, scope)
    return {
        "task": task,
        "shown_in_chat": True,
        **({"empty": True, "message": outcome["message"]} if outcome.get("empty") else {}),
    }


def _run_one_review(
    store: SessionStore,
    task: str,
    args: dict,
    emitter: Emitter,
    scope: str,
) -> dict[str, object]:
    """Run a single review task using the current session credential."""
    params = {
        "repo_path": str(store.root),
        "branch": str(args.get("branch") or ""),
        "commit_range": str(args.get("commit_range") or ""),
    }
    if task == "review_git":
        review_scope = inspect_git_review_scope(
            params["repo_path"],
            commit_range=params["commit_range"],
            branch=params["branch"],
        )
        if review_scope.empty:
            report = _empty_git_review_report(review_scope)
            store.active.add_message("assistant", report)
            emitter.chat_delta(report)
            emitter.chat_done(report)
            return {
                "empty": True,
                "message": review_scope.message,
            }
        # Untracked-only diffs are reviewable: surface the file list so the
        # agent knows exactly what to inspect.
        untracked = review_scope.untracked_files
        if untracked and not params["commit_range"] and not params["branch"]:
            params["untracked_hint"] = "\n".join(
                f"- 未跟踪文件（新增）：{path}" for path in untracked
            )
    config = _session_config(store)
    if config is None:
        raise ValueError(_login_hint())
    emitter.status("scanning", f"{scope}：{task}")
    report = asyncio.run(_run_chat_review(task, config, params, emitter))
    if report:
        store.active.add_message("assistant", report)
    if task == "arch_overview" and report:
        store.remember_project_context(report)
    return {"empty": False, "message": ""}


def _empty_git_review_report(scope: GitReviewScope) -> str:
    """Return a deterministic report when there is no tracked diff to review."""
    details = [scope.message]
    if scope.files:
        details.extend(f"- `{path}`" for path in scope.files[:20])
        if len(scope.files) > 20:
            details.append(f"- 其余 {len(scope.files) - 20} 个未跟踪文件未列出")
    return "\n".join(
        [
            "# Git 变更审查：未检测到变更",
            "",
            "## 变更概览",
            *details,
            "",
            "## 高严重度问题",
            "无。",
            "",
            "## 中严重度问题",
            "无。",
            "",
            "## 低严重度问题",
            "无。",
            "",
            "## 结论",
            "没有可审查的 tracked diff，未调用模型。",
        ]
    )


async def _run_chat_review(
    task: str,
    config: Config,
    params: dict[str, str],
    emitter: Emitter,
) -> str:
    """Run one review agent and surface the final markdown as chat content."""
    agent = build_agent(task, config)
    report = await _collect_review(agent, task, params, emitter)
    if report:
        emitter.chat_delta(report)
        emitter.chat_done(report)
    else:
        raise ValueError(f"{task} 没有生成报告内容，请稍后重试或检查模型输出限制")
    return report


async def _collect_review(
    agent: Agent,
    task: str,
    params: dict[str, str],
    emitter: Emitter,
) -> str:
    """Collect the final review markdown while retaining progress events."""
    user_prompt = get_user_prompt(task, params)
    parts: list[str] = []
    final_text = ""
    calls: dict[str, list] = {}
    results: dict[str, list[str]] = {}
    truncated = False
    async for event in agent.reply_stream(
        Msg(
            name="user",
            content=[TextBlock(type="text", text=user_prompt)],
            role="user",
        ),
        yield_final_msg=True,
    ):
        if isinstance(event, Msg):
            text = (event.get_text_content() or "").strip()
            if text:
                final_text = text
            continue
        event_type = getattr(event, "type", None)
        if event_type == EventType.TEXT_BLOCK_DELTA:
            if isinstance(event, TextBlockDeltaEvent) and event.delta:
                parts.append(event.delta)
        elif event_type == EventType.THINKING_BLOCK_DELTA:
            if getattr(event, "delta", ""):
                emitter.think_delta(event.delta)
        elif event_type in {
            EventType.TOOL_CALL_START,
            EventType.TOOL_CALL_DELTA,
            EventType.TOOL_CALL_END,
            EventType.TOOL_RESULT_TEXT_DELTA,
            EventType.TOOL_RESULT_END,
        }:
            _forward_tool_event(event, emitter, calls, results)
        elif event_type == EventType.REPLY_END:
            # A reply that ends without completing usually means the model hit
            # its output token limit; flag it so the user is not left with a
            # silently clipped report.
            if getattr(event, "finished_reason", None) != "completed":
                truncated = True
    report = (final_text or "".join(parts)).strip()
    if not report:
        # Some providers only expose the final answer through agent context.
        last_msg = agent._get_last_msg()  # noqa: SLF001
        if last_msg is not None:
            report = (last_msg.get_text_content() or "").strip()
    if report and truncated:
        report += (
            "\n\n> 报告可能因达到模型输出长度上限而被截断，"
            "可在 `.env` 中调大 `EXHIBIT_MAX_OUTPUT_TOKENS` 后重试。"
        )
    return report


def _login_hint() -> str:
    """Explain why chat cannot start and which command unblocks it."""
    if len(load_credentials()) > 1:
        return (
            "检测到多个已登录供应商，请先用 /provider 选择，"
            "或设置 EXHIBIT_PROVIDER。"
        )
    return "尚未配置可用的模型登录，请先输入 /login。"


def _session_config(store: SessionStore) -> Config | None:
    """Resolve the active provider credential into a model config."""
    session = store.active
    if session.api_key and session.base_url and session.model:
        return Config(
            base_url=session.base_url,
            api_key=session.api_key,
            model=session.model,
            max_iters=60,
            request_timeout=600,
            max_output_tokens=16000,
        )
    saved = load_credentials()
    requested = (
        session.provider or os.getenv("EXHIBIT_PROVIDER", "")
    ).strip().lower()
    credential = saved.get(requested) if requested else None
    if credential is None and len(saved) == 1:
        credential = next(iter(saved.values()))
    if credential is None:
        return None
    session.configure(credential)
    return Config(
        base_url=credential.base_url,
        api_key=credential.api_key,
        model=credential.model,
        max_iters=60,
        request_timeout=600,
        max_output_tokens=16000,
    )


async def _chat_once(agent: Agent, text: str, emitter: Emitter) -> str:
    """Stream one chat response and return its complete text."""
    parts: list[str] = []
    calls: dict[str, list] = {}
    results: dict[str, list[str]] = {}
    async for event in agent.reply_stream(
        Msg(
            name="user",
            content=[TextBlock(type="text", text=text)],
            role="user",
        ),
        yield_final_msg=True,
    ):
        if isinstance(event, Msg):
            final = (event.get_text_content() or "").strip()
            if final:
                parts[:] = [final]
            continue
        if getattr(event, "type", None) == EventType.TEXT_BLOCK_DELTA:
            if isinstance(event, TextBlockDeltaEvent) and event.delta:
                parts.append(event.delta)
                emitter.chat_delta(event.delta)
        elif getattr(event, "type", None) in {
            EventType.TOOL_CALL_START,
            EventType.TOOL_CALL_DELTA,
            EventType.TOOL_CALL_END,
            EventType.TOOL_RESULT_TEXT_DELTA,
            EventType.TOOL_RESULT_END,
        }:
            _forward_tool_event(event, emitter, calls, results)
        elif getattr(event, "type", None) == EventType.THINKING_BLOCK_DELTA:
            if getattr(event, "delta", ""):
                emitter.think_delta(event.delta)
    reply = "".join(parts).strip()
    if not reply:
        raise ValueError(
            "模型没有返回任何内容；请检查 OpenRouter 模型权限或稍后重试"
        )
    return reply


if __name__ == "__main__":
    raise SystemExit(main())
