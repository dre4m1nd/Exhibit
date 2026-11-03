/** Pure text formatters for command results, session status and tool args. */

/**
 * Human-readable result for slash commands that don't open a dedicated screen
 * or stream a report. Returns "" for commands without a meaningful result line
 * so callers can skip echoing. Keeping this pure makes every command's result
 * echoable and unit-testable, and covers commands the chat previously dropped.
 */
export function describeCommandResult(
  name: string,
  data: Record<string, unknown>,
): string {
  switch (name) {
    case "/logout":
      return `已退出登录 ${String(data.provider ?? "")}`;
    case "/clear":
      return "对话上下文已清空";
    case "/compact":
      return `已压缩上下文，保留 ${String(data.messages ?? 0)} 条，文件变更：${
        Array.isArray(data.changed_files)
          ? (data.changed_files as unknown[]).join(", ") || "无"
          : "无"
      }`;
    case "/permissions":
      return `模式 ${String(data.mode ?? "")} · 写入权限 ${
        data.writes ? "开启" : "仅只读"
      } · 确认策略 ${String(data.confirmation ?? "")}`;
    case "/files":
      return `已读 ${formatList(data.read_files)} · 已改 ${formatList(data.changed_files)}`;
    case "/undo":
      return data.undone ? `已撤销：${String(data.undone)}` : "没有可撤销的修改";
    case "/commands":
      return formatCommands(data.commands);
    default:
      return `${name}: ${JSON.stringify(data)}`;
  }
}

/** Commands arrive as `{name, description}` objects, not plain strings. */
function formatCommands(value: unknown): string {
  const rows = Array.isArray(value) ? (value as unknown[]) : [];
  const lines = rows
    .map((item) => {
      if (item && typeof item === "object") {
        const record = item as Record<string, unknown>;
        const name = String(record.name ?? "").trim();
        const description = String(record.description ?? "").trim();
        if (name) return description ? `${name} · ${description}` : name;
      }
      return String(item ?? "").trim();
    })
    .filter((line) => line.length > 0);
  if (lines.length === 0) return "没有可用命令";
  return ["可用命令：", ...lines].join("\n");
}

function formatList(value: unknown, prefix = ""): string {
  const items = Array.isArray(value)
    ? (value as unknown[]).map((item) =>
        item && typeof item === "object" ? JSON.stringify(item) : String(item),
      )
    : [];
  if (items.length === 0) return prefix ? `${prefix}无` : "无";
  return prefix ? `${prefix}${items.join(", ")}` : items.join(", ");
}

/**
 * Status-bar text for a session event.
 *
 * Carries the mode plus the provider and model the agent will really call, so
 * the bar never has to guess from environment defaults.
 */
export function sessionStatus(data: Record<string, unknown>): string {
  const parts = [String(data.session ?? "main")];
  if (String(data.mode ?? "") === "plan") parts.push("plan");
  const provider = String(data.provider ?? "");
  const model = String(data.model ?? "");
  if (provider || model) {
    parts.push([provider, model].filter(Boolean).join(" · "));
  }
  return `会话 ${parts.join(" · ")}`;
}

export function formatStatus(data: Record<string, unknown>): string {
  return Object.entries(data)
    .map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(", ") : String(value)}`)
    .join("\n");
}

export function formatArgs(args: Record<string, unknown>): string {
  return Object.entries(args)
    .map(([key, value]) => `${key}=${typeof value === "string" ? value : JSON.stringify(value)}`)
    .join(", ");
}
