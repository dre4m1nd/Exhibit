/** Slash commands shown inline while the user types `/`. */

export interface SlashCommand {
  name: string;
  description: string;
  requiresConfirm?: boolean;
}

export interface Suggestion {
  label: string;
  description: string;
  insert: string;
  kind: "command" | "review";
  execute?: string;
  takesArguments?: boolean;
}

export const SLASH_COMMANDS: SlashCommand[] = [
  { name: "/login", description: "配置模型供应商与 API Key" },
  { name: "/logout", description: "删除当前供应商凭据", requiresConfirm: true },
  { name: "/provider", description: "查看或切换模型供应商" },
  { name: "/model", description: "查看或切换模型" },
  { name: "/status", description: "查看当前会话状态" },
  { name: "/init", description: "生成架构总览与项目上下文" },
  { name: "/clear", description: "清空当前对话上下文", requiresConfirm: true },
  { name: "/compact", description: "压缩当前对话上下文" },
  { name: "/plan", description: "进入或退出计划模式" },
  { name: "/fork", description: "从当前对话创建分支会话" },
  { name: "/review", description: "选择审查类型：arch、audit、repo 或 git" },
  { name: "/diff", description: "审查当前 Git 变更" },
  { name: "/permissions", description: "查看文件写入权限" },
  { name: "/files", description: "查看本轮读取或修改的文件" },
  { name: "/undo", description: "撤销最近一次可恢复的文件修改" },
  { name: "/quit", description: "退出 Exhibit" },
];

/** Commands whose agent-side handler requires an explicit confirmation. */
const DESTRUCTIVE = new Set(["/clear", "/logout"]);

/** Commands that take free-form arguments, so Enter should not run them blind. */
export const TAKES_ARGUMENTS = new Set(["/review", "/diff"]);

/** The four review modes accepted by `/review`. */
export const REVIEW_TASKS = [
  { value: "arch", description: "架构总览：模块职责、依赖关系与阅读路径" },
  { value: "audit", description: "架构审查：越层调用、循环依赖与职责失衡" },
  { value: "repo", description: "整仓审查：正确性、安全、可维护性与测试缺口" },
  { value: "git", description: "Git 变更：未提交改动、commit range 或分支 diff" },
] as const;

/** How many suggestion rows the palette shows at once. */
export const PALETTE_HEIGHT = 6;

/**
 * Return commands matching the current slash prefix.
 *
 * Candidates only appear while the user is still naming a command: an empty
 * input, ordinary chat text, or a line that already contains a space (that is,
 * arguments have started) all yield no suggestions.
 */
export function availableCommands(
  input: string,
  planMode: boolean,
): SlashCommand[] {
  if (!input.startsWith("/") || input.includes(" ")) return [];
  const prefix = input.toLowerCase();
  return SLASH_COMMANDS.filter((command) => command.name.startsWith(prefix)).filter(
    (command) => !(planMode && command.name === "/undo"),
  );
}

/**
 * Return the review modes once the user has committed to `/review`.
 *
 * The command palette remains quiet for free-form text, but the structured
 * review arguments are discoverable as soon as a trailing space is typed.
 */
export function suggestionsFor(
  input: string,
  planMode: boolean,
): Suggestion[] {
  const normalized = input.toLowerCase();
  if (normalized.startsWith("/review ")) {
    const fragment = input.slice("/review ".length).trim().toLowerCase();
    if (fragment.includes(",") || /\s/.test(fragment)) return [];
    const matches = REVIEW_TASKS.filter((task) =>
      task.value.startsWith(fragment),
    );
    // A trailing space means the user has not typed a mode yet. Show the
    // four modes instead of guessing a default review.
    if (!fragment) {
      return REVIEW_TASKS.map((task) => ({
        label: task.value,
        description: task.description,
        insert: `/review ${task.value}`,
        kind: "review",
        execute: `/review ${task.value}`,
      }));
    }
    return matches.map(
      (task) => ({
        label: task.value,
        description: task.description,
        insert: `/review ${task.value}`,
        kind: "review",
        execute: `/review ${task.value}`,
      }),
    );
  }
  return availableCommands(input, planMode).map((command) => ({
    label: command.name,
    description: command.description,
    insert: command.name,
    kind: "command",
    execute: TAKES_ARGUMENTS.has(command.name) ? undefined : command.name,
    takesArguments: TAKES_ARGUMENTS.has(command.name),
  }));
}

/** Move a highlight index by `delta`, wrapping around; -1 when empty. */
export function moveSelection(
  current: number,
  delta: number,
  total: number,
): number {
  if (total <= 0) return -1;
  const start = current < 0 ? 0 : current;
  return (((start + delta) % total) + total) % total;
}

/** Start/end of the visible slice, keeping `index` inside it. */
export function windowAround(
  index: number,
  total: number,
  height: number,
): { start: number; end: number } {
  if (total <= 0) return { start: 0, end: 0 };
  const size = Math.max(1, Math.min(height, total));
  const clamped = Math.max(0, Math.min(index, total - 1));
  // Centre the highlight, then clamp so the window never leaves the list.
  const centered = clamped - Math.floor(size / 2);
  const start = Math.max(0, Math.min(centered, total - size));
  return { start, end: start + size };
}

/** Parse the small flag grammar used by `/review` and `/diff`. */
export function parseCommandArgs(
  command: string,
  parts: string[],
): Record<string, unknown> {
  const normalized = command.trim().toLowerCase();
  // Destructive commands need an explicit second confirmation in the agent.
  if (DESTRUCTIVE.has(normalized) && !parts.includes("--confirm")) {
    return { confirm: false };
  }
  if (command === "/provider" || command === "/model") {
    return parts[0] ? { [command.slice(1)]: parts[0] } : {};
  }
  const result: Record<string, unknown> = {};
  if (DESTRUCTIVE.has(normalized)) result.confirm = true;
  const freeText: string[] = [];
  for (let index = 0; index < parts.length; index += 1) {
    const part = parts[index];
    if (part === undefined) continue;
    if (part === "--range" || part === "--commit-range") {
      const value = parts[index + 1];
      if (value && !value.startsWith("--")) result.commit_range = value;
      index += 1;
    } else if (part === "--branch") {
      const value = parts[index + 1];
      if (value && !value.startsWith("--")) result.branch = value;
      index += 1;
    } else if (!part.startsWith("--")) {
      freeText.push(part);
    }
  }
  // Keep natural-language arguments intact. The agent splits explicit
  // multi-task syntax on commas, while "审查这个项目的架构" must remain one
  // phrase instead of becoming "审查,这个项目的,架构".
  if (command === "/review" && freeText.length > 0) {
    result.task = freeText.join(" ");
  }
  return result;
}

