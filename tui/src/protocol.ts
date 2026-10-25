/** The JSON-line protocol mirrored from `agent/protocol.py`. */

export const TASKS = [
  "arch_overview",
  "arch_audit",
  "review_repo",
  "review_git",
] as const;

export type TaskName = (typeof TASKS)[number];

export const TASK_TITLES: Record<TaskName, string> = {
  arch_overview: "架构总览与模块职责",
  arch_audit: "架构失职审查",
  review_repo: "整仓代码审查",
  review_git: "Git 变更审查",
};

export type AgentMessage =
  | { type: "status"; phase: string; detail: string }
  | { type: "tool_call"; name: string; args: Record<string, unknown> }
  | { type: "tool_result"; name: string; ok: boolean; summary: string }
  | { type: "token"; text: string }
  | { type: "reset" }
  | { type: "report"; markdown: string }
  | { type: "error"; message: string }
  | { type: "done" };

/** Parse one stdout line; unknown or malformed lines are dropped. */
export function parseLine(line: string): AgentMessage | null {
  try {
    const value: unknown = JSON.parse(line);
    if (typeof value !== "object" || value === null) return null;
    const record = value as Record<string, unknown>;
    const type = record.type;
    if (typeof type !== "string") return null;
    switch (type) {
      case "status":
        return {
          type,
          phase: String(record.phase ?? ""),
          detail: String(record.detail ?? ""),
        };
      case "tool_call":
        return {
          type,
          name: String(record.name ?? ""),
          args: (record.args as Record<string, unknown>) ?? {},
        };
      case "tool_result":
        return {
          type,
          name: String(record.name ?? ""),
          ok: Boolean(record.ok),
          summary: String(record.summary ?? ""),
        };
      case "token":
        return { type, text: String(record.text ?? "") };
      case "reset":
        return { type };
      case "report":
        return { type, markdown: String(record.markdown ?? "") };
      case "error":
        return { type, message: String(record.message ?? "") };
      case "done":
        return { type };
      default:
        return null;
    }
  } catch {
    return null;
  }
}
