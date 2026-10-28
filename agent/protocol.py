# -*- coding: utf-8 -*-
"""The JSON-line protocol shared by the Python agent and the Ink TUI.

Every message is a single line of UTF-8 JSON written to stdout (agent side) or
stdin (TUI side). Anything written to stderr stays out of the protocol and is
treated as a subprocess log line.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Literal

# TUI -> agent
MSG_INIT = "init"
MSG_CHAT = "chat"
MSG_COMMAND = "command"
MSG_PERMISSION_RESPONSE = "permission_response"

# agent -> TUI
MSG_STATUS = "status"
MSG_TOOL_CALL = "tool_call"
MSG_TOOL_RESULT = "tool_result"
MSG_TOKEN = "token"
MSG_RESET = "reset"
MSG_REPORT = "report"
MSG_ERROR = "error"
MSG_DONE = "done"
MSG_CHAT_DELTA = "chat_delta"
MSG_CHAT_DONE = "chat_done"
MSG_THINKING = "thinking_delta"
MSG_COMMAND_RESULT = "command_result"
MSG_PERMISSION_REQUEST = "permission_request"
MSG_SESSION = "session"

TaskName = Literal["arch_overview", "arch_audit", "review_repo", "review_git"]

TaskTitles: dict[str, str] = {
    "arch_overview": "架构总览与模块职责",
    "arch_audit": "架构失职审查",
    "review_repo": "整仓代码审查",
    "review_git": "Git 变更审查",
}

TASKS: tuple[str, ...] = tuple(TaskTitles)


class ProtocolError(ValueError):
    """Raised when an incoming line is not a valid protocol message."""


def encode(message: dict[str, Any]) -> str:
    """Serialize a message to a single JSON line."""
    return json.dumps(message, ensure_ascii=False, separators=(",", ":"))


def decode(line: str) -> dict[str, Any]:
    """Parse one JSON line into a message dict.

    Raises:
        ProtocolError: The line is not a JSON object.
    """
    try:
        message = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"invalid JSON line: {exc}") from exc
    if not isinstance(message, dict):
        raise ProtocolError("protocol message must be a JSON object")
    if "type" not in message:
        raise ProtocolError("protocol message is missing the 'type' field")
    return message


class Emitter:
    """Writes protocol messages to a stream, one JSON object per line."""

    def __init__(self, stream: Any = None) -> None:
        self._stream = stream if stream is not None else sys.stdout

    def send(self, message: dict[str, Any]) -> None:
        self._stream.write(encode(message) + "\n")
        self._stream.flush()

    def status(self, phase: str, detail: str = "") -> None:
        self.send({"type": MSG_STATUS, "phase": phase, "detail": detail})

    def tool_call(self, name: str, args: Any = None) -> None:
        self.send({"type": MSG_TOOL_CALL, "name": name, "args": args or {}})

    def tool_result(self, name: str, ok: bool, summary: str = "") -> None:
        self.send(
            {
                "type": MSG_TOOL_RESULT,
                "name": name,
                "ok": ok,
                "summary": summary,
            }
        )

    def token(self, text: str) -> None:
        if text:
            self.send({"type": MSG_TOKEN, "text": text})

    def reset(self) -> None:
        """Tell the TUI to discard the current streaming draft."""
        self.send({"type": MSG_RESET})

    def report(self, markdown: str) -> None:
        self.send({"type": MSG_REPORT, "markdown": markdown})

    def error(self, message: str) -> None:
        self.send({"type": MSG_ERROR, "message": message})

    def done(self) -> None:
        self.send({"type": MSG_DONE})

    def chat_delta(self, text: str) -> None:
        if text:
            self.send({"type": MSG_CHAT_DELTA, "text": text})

    def chat_done(self, text: str = "") -> None:
        self.send({"type": MSG_CHAT_DONE, "text": text})

    def think_delta(self, text: str) -> None:
        """Stream a model reasoning chunk for the TUI's collapsible trace."""
        if text:
            self.send({"type": MSG_THINKING, "text": text})

    def command_result(self, name: str, data: Any = None) -> None:
        self.send({"type": MSG_COMMAND_RESULT, "name": name, "data": data or {}})

    def permission_request(
        self,
        request_id: str,
        path: str,
        action: str,
        summary: str,
        session_id: str = "main",
        trusted: bool = False,
    ) -> None:
        self.send(
            {
                "type": MSG_PERMISSION_REQUEST,
                "request_id": request_id,
                "path": path,
                "action": action,
                "summary": summary,
                "session_id": session_id,
                "trusted": trusted,
            }
        )

    def session(self, data: dict[str, Any]) -> None:
        self.send({"type": MSG_SESSION, "data": data})
