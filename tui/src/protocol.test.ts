import { describe, expect, it } from "vitest";
import { parseLine, TASKS, TASK_TITLES } from "./protocol.js";

describe("parseLine", () => {
  it("parses a status message", () => {
    expect(
      parseLine('{"type":"status","phase":"tool","detail":"调用 list_dir"}'),
    ).toEqual({ type: "status", phase: "tool", detail: "调用 list_dir" });
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
});
