import { describe, expect, it } from "vitest";
import { parseLine, TASKS, TASK_TITLES } from "./protocol.js";

describe("parseLine", () => {
  it("parses a status message", () => {
    expect(
      parseLine('{"type":"status","phase":"tool","detail":"调用 list_dir"}'),
    ).toEqual({ type: "status", phase: "tool", detail: "调用 list_dir" });
  });

  it("parses a thinking_delta message", () => {
    expect(
      parseLine('{"type":"thinking_delta","text":"先分析入口"}'),
    ).toEqual({ type: "thinking_delta", text: "先分析入口" });
  });

  it("parses a tool_call message with args", () => {
    expect(
      parseLine('{"type":"tool_call","name":"read_file","args":{"path":"a.py"}}'),
    ).toEqual({ type: "tool_call", name: "read_file", args: { path: "a.py" } });
  });

  it("parses a tool_result message", () => {
    expect(
      parseLine('{"type":"tool_result","name":"grep_files","ok":true,"summary":"3 hits"}'),
    ).toEqual({ type: "tool_result", name: "grep_files", ok: true, summary: "3 hits" });
  });

  it("parses token, report, error and done messages", () => {
    expect(parseLine('{"type":"token","text":"hi"}')).toEqual({ type: "token", text: "hi" });
    expect(parseLine('{"type":"reset"}')).toEqual({ type: "reset" });
    expect(parseLine('{"type":"report","markdown":"# T"}')).toEqual({
      type: "report",
      markdown: "# T",
    });
    expect(parseLine('{"type":"error","message":"boom"}')).toEqual({
      type: "error",
      message: "boom",
    });
    expect(parseLine('{"type":"done"}')).toEqual({ type: "done" });
    expect(parseLine('{"type":"chat_delta","text":"hi"}')).toEqual({
      type: "chat_delta",
      text: "hi",
    });
    expect(parseLine('{"type":"chat_done","text":"done"}')).toEqual({
      type: "chat_done",
      text: "done",
    });
    expect(
      parseLine('{"type":"command_result","name":"/status","data":{"mode":"plan"}}'),
    ).toEqual({
      type: "command_result",
      name: "/status",
      data: { mode: "plan" },
    });
    expect(
      parseLine(
        '{"type":"permission_request","request_id":"p1","path":"a.py","action":"覆盖","summary":"1 → 2 行"}',
      ),
    ).toEqual({
      type: "permission_request",
      request_id: "p1",
      path: "a.py",
      action: "覆盖",
      summary: "1 → 2 行",
      session_id: "main",
      trusted: false,
    });
    expect(parseLine('{"type":"session","data":{"session":"main"}}')).toEqual({
      type: "session",
      data: { session: "main" },
    });
  });

  it("drops malformed, unknown and non-object lines", () => {
    expect(parseLine("not json")).toBeNull();
    expect(parseLine("")).toBeNull();
    expect(parseLine("42")).toBeNull();
    expect(parseLine('{"nope":1}')).toBeNull();
    expect(parseLine('{"type":"unknown_event"}')).toBeNull();
  });

  it("keeps the task list aligned with the Python side", () => {
    expect(TASKS).toHaveLength(4);
    for (const task of TASKS) {
      expect(TASK_TITLES[task]).toBeTruthy();
    }
  });

  it("carries the session id and session-trust flag on permission requests", () => {
    expect(
      parseLine(
        '{"type":"permission_request","request_id":"p2","path":"b.py","action":"替换","summary":"1 → 2 行","session_id":"fork-01","trusted":true}',
      ),
    ).toEqual({
      type: "permission_request",
      request_id: "p2",
      path: "b.py",
      action: "替换",
      summary: "1 → 2 行",
      session_id: "fork-01",
      trusted: true,
    });
  });
});
