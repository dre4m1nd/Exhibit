/** Collapsible "run trace" steps emitted while the agent thinks and acts. */

export interface TraceStep {
  type: "thinking" | "tool" | "tool-result";
  text: string;
  ok?: boolean;
}

/**
 * Append a streamed step, merging adjacent thinking deltas into one segment.
 *
 * Providers often emit reasoning a few characters at a time. Keeping every
 * delta as a separate row makes the expanded trace unreadable, so a new tool
 * event is the only thing that starts a fresh thinking segment.
 */
export function appendTraceStep(
  steps: TraceStep[],
  step: TraceStep,
): TraceStep[] {
  const last = steps[steps.length - 1];
  if (step.type === "thinking" && last?.type === "thinking") {
    return [
      ...steps.slice(0, -1),
      { ...last, text: last.text + step.text },
    ];
  }
  return [...steps, step];
}

/**
 * Count reasoning segments in a step list.
 *
 * A segment is one continuous run of thinking, and a new run after a tool step
 * counts as another segment, so "think → act → observe → think" is two segments.
 */
export function countThinkingSegments(steps: TraceStep[]): number {
  let segments = 0;
  let inThinking = false;
  for (const step of steps) {
    if (step.type === "thinking") {
      if (!inThinking) segments += 1;
      inThinking = true;
    } else {
      inThinking = false;
    }
  }
  return segments;
}

/**
 * Produce a one-line count summary for a collapsed trace.
 * Returns an empty string when there is nothing to show.
 */
export function summarizeTrace(steps: TraceStep[]): string {
  if (steps.length === 0) return "";
  const thinking = countThinkingSegments(steps);
  const tools = steps.filter((step) => step.type === "tool").length;
  const parts: string[] = [];
  if (thinking > 0) parts.push(`思考 ${thinking} 步`);
  if (tools > 0) parts.push(`调用工具 ${tools} 次`);
  return parts.join(" · ");
}

/** Describe the most recent activity in a compact, user-facing form. */
export function latestTraceActivity(steps: TraceStep[]): string {
  const last = steps[steps.length - 1];
  if (!last) return "";
  if (last.type === "thinking") return "思考中";

  const name = last.text.split(/[(→]/)[0]?.trim() || "工具";
  if (last.type === "tool") return `正在 ${name}`;
  return last.ok === false ? `${name} 失败` : `${name} 已完成`;
}

