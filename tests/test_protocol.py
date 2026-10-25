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
    emitter.done()
    lines = stream.getvalue().strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["type"] == "status"
    assert json.loads(lines[1])["type"] == "done"


def test_init_constant() -> None:
    assert MSG_INIT == "init"


def test_reset_event_is_emitted() -> None:
    stream = io.StringIO()
    Emitter(stream).reset()
    assert json.loads(stream.getvalue())["type"] == "reset"
