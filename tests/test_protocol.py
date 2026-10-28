# -*- coding: utf-8 -*-
"""Tests for the JSON-line protocol encoder/decoder."""

from __future__ import annotations

import io
import json

import pytest

from agent.protocol import (
    MSG_INIT,
    Emitter,
    ProtocolError,
    TASKS,
    decode,
    encode,
)


def test_roundtrip() -> None:
    message = {"type": "status", "phase": "tool", "detail": "调用 list_dir"}
    assert decode(encode(message)) == message


def test_encode_keeps_text_on_one_line() -> None:
    line = encode({"type": "token", "text": "line1\nline2"})
    assert "\n" in json.loads(line)["text"]
    assert line.count("\n") == 0


def test_decode_rejects_invalid_lines() -> None:
    with pytest.raises(ProtocolError):
        decode("not json")
    with pytest.raises(ProtocolError):
        decode("42")


def test_decode_requires_type_field() -> None:
    with pytest.raises(ProtocolError, match="type"):
        decode(json.dumps({"phase": "tool"}))


def test_task_names_are_four() -> None:
    assert TASKS == (
        "arch_overview",
        "arch_audit",
        "review_repo",
        "review_git",
    )


def test_emitter_writes_one_json_object_per_line() -> None:
    stream = io.StringIO()
    emitter = Emitter(stream)
    emitter.status("scanning", "准备")
    emitter.chat_delta("你好")
    emitter.chat_done("你好")
    emitter.command_result("/status", {"mode": "plan"})
    emitter.permission_request(
        "p1", "a.py", "覆盖", "1 → 2 行", session_id="fork-01"
    )
    emitter.session({"session": "main"})
    emitter.done()
    lines = stream.getvalue().strip().split("\n")
    assert len(lines) == 7
    assert json.loads(lines[0])["type"] == "status"
    assert json.loads(lines[1])["type"] == "chat_delta"
    assert json.loads(lines[2])["type"] == "chat_done"
    assert json.loads(lines[3])["type"] == "command_result"
    assert json.loads(lines[4])["type"] == "permission_request"
    assert json.loads(lines[4])["session_id"] == "fork-01"
    assert json.loads(lines[5])["type"] == "session"
    assert json.loads(lines[6])["type"] == "done"


def test_init_constant() -> None:
    assert MSG_INIT == "init"


def test_reset_event_is_emitted() -> None:
    stream = io.StringIO()
    Emitter(stream).reset()
    assert json.loads(stream.getvalue())["type"] == "reset"


def test_thinking_delta_is_emitted() -> None:
    stream = io.StringIO()
    Emitter(stream).think_delta("先看一下仓库结构")
    assert json.loads(stream.getvalue()) == {
        "type": "thinking_delta",
        "text": "先看一下仓库结构",
    }


def test_empty_thinking_delta_is_skipped() -> None:
    stream = io.StringIO()
    Emitter(stream).think_delta("")
    assert stream.getvalue() == ""
