import { describe, expect, it } from "vitest";
import {
  appendTraceStep,
  countThinkingSegments,
  latestTraceActivity,
  summarizeTrace,
  type TraceStep,
} from "./trace.js";

const thinking = (text = "思考"): TraceStep => ({ type: "thinking", text });
const tool = (name = "git_status"): TraceStep => ({ type: "tool", text: `${name}()` });
const result = (name = "git_status"): TraceStep => ({
  type: "tool-result",
  text: `${name} → ok`,
  ok: true,
});

describe("trace summary", () => {
  it("returns an empty string when there are no steps", () => {
    expect(summarizeTrace([])).toBe("");
  });

  it("counts only thinking when no tools ran", () => {
    expect(summarizeTrace([thinking(), thinking("继续分析")])).toBe("思考 1 步");
  });

  it("counts only tool calls when no thinking ran", () => {
    expect(summarizeTrace([tool(), tool("list_dir")])).toBe("调用工具 2 次");
  });

  it("joins thinking and tool counts when both exist", () => {
    expect(summarizeTrace([thinking(), tool(), result()])).toBe(
      "思考 1 步 · 调用工具 1 次",
    );
  });

  it("starts a new thinking segment after a tool step", () => {
    expect(summarizeTrace([thinking(), tool(), thinking("下一步")])).toBe(
      "思考 2 步 · 调用工具 1 次",
    );
    expect(countThinkingSegments([thinking(), tool(), thinking("下一步")])).toBe(2);
  });

  it("treats consecutive thinking as one segment", () => {
    expect(countThinkingSegments([thinking(), thinking("继续")])).toBe(1);
  });
});

describe("trace aggregation", () => {
  it("merges adjacent thinking deltas", () => {
    const steps = appendTraceStep(
      appendTraceStep([], thinking("先看")),
      thinking("结构"),
    );
    expect(steps).toEqual([thinking("先看结构")]);
  });

  it("starts a new thinking segment after a tool step", () => {
    const steps = [
      thinking("先看结构"),
      tool(),
      thinking("再读入口"),
    ].reduce(appendTraceStep, [] as TraceStep[]);
    expect(steps).toEqual([
      thinking("先看结构"),
      tool(),
      thinking("再读入口"),
    ]);
    expect(countThinkingSegments(steps)).toBe(2);
  });

  it("describes the latest tool activity", () => {
    expect(latestTraceActivity([])).toBe("");
    expect(latestTraceActivity([thinking()])).toBe("思考中");
    expect(latestTraceActivity([tool("list_dir")])).toBe("正在 list_dir");
    expect(latestTraceActivity([result("list_dir")])).toBe("list_dir 已完成");
    expect(
      latestTraceActivity([{ ...result("list_dir"), ok: false }]),
    ).toBe("list_dir 失败");
  });
});

describe("trace cap", () => {
  it("keeps at most the most recent steps", () => {
    const steps = Array.from({ length: 60 }, () => thinking("…")).reduce(
      appendTraceStep,
      [] as TraceStep[],
    );
    expect(steps.length).toBeLessThanOrEqual(40);
    // Adjacent thinking deltas merge, so the latest one is still present at the tail.
    expect(steps[steps.length - 1].text.endsWith("…")).toBe(true);
  });

  it("drops the oldest steps once the cap is exceeded", () => {
    const steps = Array.from({ length: 50 }, (_, index) => tool(`t${index}`)).reduce(
      appendTraceStep,
      [] as TraceStep[],
    );
    expect(steps.length).toBeLessThanOrEqual(40);
    expect(steps[0].text).toBe("t10()");
  });
});
