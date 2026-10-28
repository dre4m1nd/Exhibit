import { describe, expect, it } from "vitest";
import {
  buildChatLines,
  buildLiveTraceLines,
  displayWidth,
  selectVisibleLines,
  tailLines,
  wrapText,
} from "./chatLines.js";
import type { ChatMessage } from "./components/ChatView.js";

function msg(text: string, role: ChatMessage["role"] = "assistant"): ChatMessage {
  return { id: 1, role, text };
}

describe("displayWidth", () => {
  it("counts CJK characters as two cells", () => {
    expect(displayWidth("ab")).toBe(2);
    expect(displayWidth("架构")).toBe(4);
  });
});

describe("wrapText", () => {
  it("keeps short text on one line", () => {
    expect(wrapText("hello", 20)).toEqual(["hello"]);
  });

  it("wraps at the last space before the limit", () => {
    expect(wrapText("alpha beta gamma", 11)).toEqual(["alpha beta", "gamma"]);
  });

  it("hard-wraps unbroken text", () => {
    expect(wrapText("abcdefghij", 4)).toEqual(["abcd", "efgh", "ij"]);
  });

  it("accounts for wide characters", () => {
    expect(wrapText("架构总览", 4)).toEqual(["架构", "总览"]);
  });
});

describe("selectVisibleLines", () => {
  const lines = Array.from({ length: 10 }, (_, index) => ({
    key: String(index),
    text: String(index),
    tone: "text" as const,
  }));

  it("pins the newest lines to the bottom", () => {
    const visible = selectVisibleLines(lines, 4, 0);
    expect(visible.lines.map((line) => line.text)).toEqual(["6", "7", "8", "9"]);
    expect(visible.canUp).toBe(true);
    expect(visible.canDown).toBe(false);
  });

  it("scrolls back line by line", () => {
    const visible = selectVisibleLines(lines, 4, 3);
    expect(visible.lines.map((line) => line.text)).toEqual(["3", "4", "5", "6"]);
    expect(visible.canDown).toBe(true);
  });

  it("clamps an oversized offset to the oldest lines", () => {
    const visible = selectVisibleLines(lines, 4, 999);
    expect(visible.lines.map((line) => line.text)).toEqual(["0", "1", "2", "3"]);
    expect(visible.offset).toBe(6);
    expect(visible.canUp).toBe(false);
  });
});

describe("buildChatLines", () => {
  it("keeps every line of a long report", () => {
    const report = [
      "# Title",
      "",
      ...Array.from({ length: 60 }, (_, i) => `- line ${i}`),
    ].join("\n");
    const lines = buildChatLines([msg(report)], 80, false);
    expect(lines.length).toBeGreaterThan(60);
    expect(lines.some((line) => line.text.includes("line 59"))).toBe(true);
    expect(lines.some((line) => line.text.includes("Title"))).toBe(true);
  });

  it("wraps CJK prose so the tail stays reachable", () => {
    const report = "架构总览".repeat(40);
    const lines = buildChatLines([msg(report)], 20, false);
    expect(lines.length).toBeGreaterThan(10);
    expect(selectVisibleLines(lines, 5, 0).lines.length).toBe(5);
  });

  it("renders trace summaries and expanded steps", () => {
    const trace: ChatMessage = {
      id: 2,
      role: "system",
      text: "思考 1 步 · 调用工具 1 次",
      kind: "trace",
      collapsedSummary: "思考 1 步 · 调用工具 1 次",
      steps: [
        { type: "thinking", text: "先看结构" },
        { type: "tool", text: "git_status()" },
      ],
    };
    const collapsed = buildChatLines([trace], 80, false);
    expect(collapsed[0]?.text).toContain("Ctrl+T 展开");
    const expanded = buildChatLines([trace], 80, true);
    expect(expanded.some((line) => line.text.includes("先看结构"))).toBe(true);
    expect(expanded.some((line) => line.text.includes("git_status()"))).toBe(true);
  });

  it("keeps the completed trace above the assistant answer", () => {
    const trace: ChatMessage = {
      id: 1,
      role: "system",
      text: "思考 1 步",
      kind: "trace",
      collapsedSummary: "思考 1 步",
      steps: [{ type: "thinking", text: "分析入口" }],
    };
    const answer = { ...msg("结论"), id: 2 };
    const lines = buildChatLines([trace, answer], 80, false);
    const traceIndex = lines.findIndex((line) => line.text.includes("思考 1 步"));
    const answerIndex = lines.findIndex((line) => line.text === "Exhibit");
    expect(traceIndex).toBeGreaterThanOrEqual(0);
    expect(answerIndex).toBeGreaterThan(traceIndex);
  });

  it("renders the collapsed live trace with counts and latest activity", () => {
    const steps = [
      { type: "thinking" as const, text: "先看结构" },
      { type: "tool" as const, text: "list_dir()" },
    ];
    const lines = buildLiveTraceLines(steps, 80, false);
    expect(lines).toHaveLength(1);
    expect(lines[0]?.text).toContain("思考 1 步");
    expect(lines[0]?.text).toContain("调用工具 1 次");
    expect(lines[0]?.text).toContain("正在 list_dir");
  });

  it("renders an expanded live trace and omits empty traces", () => {
    const steps = [
      { type: "thinking" as const, text: "先看结构" },
      { type: "tool" as const, text: "list_dir()" },
    ];
    expect(buildLiveTraceLines([], 80, true)).toEqual([]);
    const lines = buildLiveTraceLines(steps, 80, true);
    expect(lines[0]?.text).toContain("思考 1 步");
    expect(lines[0]?.text).toContain("Ctrl+T 收起");
    expect(lines.some((line) => line.text.includes("先看结构"))).toBe(true);
  });

  it("keeps the newest rows in a bounded live trace", () => {
    const lines = buildLiveTraceLines(
      [
        { type: "tool" as const, text: "one()" },
        { type: "tool" as const, text: "two()" },
      ],
      80,
      true,
    );
    expect(tailLines(lines, 2).at(-1)?.text).toContain("two()");
  });
});
