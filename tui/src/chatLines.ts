/** Flatten chat messages into terminal lines so long reports stay scrollable. */

import { parseMarkdown } from "./components/Markdown.js";
import type { ChatMessage } from "./components/ChatView.js";
import {
  latestTraceActivity,
  summarizeTrace,
  type TraceStep,
} from "./trace.js";

export type LineTone =
  | "accent"
  | "text"
  | "muted"
  | "info"
  | "ok"
  | "danger"
  | "warn"
  | "border";

export interface DisplayLine {
  key: string;
  text: string;
  tone: LineTone;
  bold?: boolean;
  dim?: boolean;
}

/** Width of one code point in terminal cells (CJK and emoji count as two). */
export function charWidth(char: string): number {
  const code = char.codePointAt(0) ?? 0;
  if (
    code === 0 ||
    code < 32 ||
    (code >= 0x0300 && code <= 0x036f) ||
    (code >= 0xfe00 && code <= 0xfe0f)
  ) {
    return 0;
  }
  if (
    (code >= 0x1100 && code <= 0x115f) ||
    code === 0x2329 ||
    code === 0x232a ||
    (code >= 0x2e80 && code <= 0xa4cf) ||
    (code >= 0xac00 && code <= 0xd7a3) ||
    (code >= 0xf900 && code <= 0xfaff) ||
    (code >= 0xfe30 && code <= 0xfe6f) ||
    (code >= 0xff00 && code <= 0xff60) ||
    (code >= 0xffe0 && code <= 0xffe6) ||
    (code >= 0x1f300 && code <= 0x1faff) ||
    (code >= 0x20000 && code <= 0x3fffd)
  ) {
    return 2;
  }
  return 1;
}

export function displayWidth(text: string): number {
  let width = 0;
  for (const char of text) width += charWidth(char);
  return width;
}

/** Hard-wrap text by terminal cell width, preferring the last space. */
export function wrapText(text: string, width: number): string[] {
  const limit = Math.max(1, Math.floor(width));
  const lines: string[] = [];
  let current = "";
  let currentWidth = 0;
  let lastSpace = -1;

  const flush = () => {
    lines.push(current.trimEnd());
    current = "";
    currentWidth = 0;
    lastSpace = -1;
  };

  for (const char of text) {
    const size = charWidth(char);
    if (currentWidth + size > limit && current.length > 0) {
      if (lastSpace > 0) {
        const carry = current.slice(lastSpace + 1);
        current = current.slice(0, lastSpace).trimEnd();
        flush();
        current = carry;
        currentWidth = displayWidth(carry);
        lastSpace = current.lastIndexOf(" ");
      } else {
        flush();
      }
    }
    current += char;
    currentWidth += size;
    if (char === " ") lastSpace = current.length - 1;
  }
  if (current.length > 0 || lines.length === 0) lines.push(current.trimEnd());
  return lines;
}

/** Drop lightweight inline markdown markers while keeping their content. */
function plainInline(text: string): string {
  return text
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/__([^_]+)__/g, "$1");
}

function prefixedLines(
  text: string,
  width: number,
  prefix: string,
  tone: LineTone,
  key: string,
  options: { bold?: boolean; dim?: boolean } = {},
): DisplayLine[] {
  const available = Math.max(1, width - displayWidth(prefix));
  const wrapped = wrapText(plainInline(text), available);
  return wrapped.map((line, index) => ({
    key: `${key}:${index}`,
    text: index === 0 ? `${prefix}${line}` : `${" ".repeat(displayWidth(prefix))}${line}`,
    tone,
    ...options,
  }));
}

function markdownLines(
  source: string,
  width: number,
  key: string,
  tone: LineTone,
): DisplayLine[] {
  const lines: DisplayLine[] = [];
  parseMarkdown(source).forEach((block, blockIndex) => {
    const blockKey = `${key}:b${blockIndex}`;
    switch (block.kind) {
      case "heading":
        lines.push(
          ...prefixedLines(
            block.text,
            width,
            block.level <= 2 ? "▌ " : "• ",
            "accent",
            blockKey,
            { bold: true },
          ),
        );
        break;
      case "bullet":
        lines.push(
          ...prefixedLines(block.text, width, "• ", tone, blockKey),
        );
        break;
      case "quote":
        lines.push(
          ...prefixedLines(block.text, width, "▌ ", "muted", blockKey, {
            dim: true,
          }),
        );
        break;
      case "code":
        block.text.split("\n").forEach((codeLine, lineIndex) => {
          lines.push(
            ...prefixedLines(
              codeLine || " ",
              width,
              "  ",
              "ok",
              `${blockKey}:${lineIndex}`,
            ),
          );
        });
        break;
      case "table":
        block.rows.forEach((row, rowIndex) => {
          lines.push(
            ...prefixedLines(
              row.join(" │ "),
              width,
              rowIndex === 0 ? "▌ " : "  ",
              rowIndex === 0 ? "accent" : tone,
              `${blockKey}:${rowIndex}`,
              { bold: rowIndex === 0 },
            ),
          );
        });
        break;
      case "rule":
        lines.push({
          key: blockKey,
          text: "─".repeat(Math.min(Math.max(1, width), 40)),
          tone: "border",
        });
        break;
      default:
        lines.push(...prefixedLines(block.text, width, "", tone, blockKey));
        break;
    }
  });
  return lines;
}

function traceLines(
  steps: TraceStep[],
  summary: string,
  expanded: boolean,
  width: number,
  key: string,
): DisplayLine[] {
  if (!expanded) {
    if (!summary) return [];
    return [
      {
        key,
        text: `▸ ${summary} · Ctrl+T 展开`,
        tone: "muted",
      },
    ];
  }
  return [
    {
      key: `${key}:summary`,
      text: `▾ ${summary} · Ctrl+T 收起`,
      tone: "muted" as const,
    },
    ...traceStepLines(steps, width, key),
  ];
}

function traceStepLines(
  steps: TraceStep[],
  width: number,
  key: string,
): DisplayLine[] {
  return steps.flatMap((step, index) => {
    const stepKey = `${key}:${index}`;
    if (step.type === "thinking") {
      return prefixedLines(step.text, width, "🜂 ", "muted", stepKey, {
        dim: true,
      });
    }
    const isCall = step.type === "tool";
    const prefix = isCall ? "▸ " : step.ok === false ? "✕ " : "✓ ";
    return prefixedLines(
      step.text,
      width,
      prefix,
      isCall ? "info" : step.ok === false ? "danger" : "ok",
      stepKey,
      { dim: !isCall },
    );
  });
}

/**
 * Render the live execution strip shown immediately above the composer.
 *
 * Collapsed mode stays useful in one line: counts plus the current activity.
 * Expanded mode reveals the accumulated steps without changing history order.
 */
export function buildLiveTraceLines(
  steps: TraceStep[],
  width: number,
  expanded: boolean,
): DisplayLine[] {
  if (steps.length === 0) return [];
  const summary = summarizeTrace(steps);
  if (!expanded) {
    const activity = latestTraceActivity(steps);
    const text = [summary, activity].filter(Boolean).join(" · ");
    return prefixedLines(text, width, "◐ ", "accent", "live-trace", {
      bold: true,
    });
  }
  return [
    {
      key: "live-trace:header",
      text: `◐ ${summary} · Ctrl+T 收起`,
      tone: "accent",
      bold: true,
    },
    ...traceStepLines(steps, width, "live-trace"),
  ];
}

/** Keep the newest trace rows visible when the terminal cannot fit them all. */
export function tailLines(
  lines: DisplayLine[],
  height: number,
): DisplayLine[] {
  const size = Math.max(1, Math.floor(height));
  return lines.length <= size ? lines : lines.slice(-size);
}

/** Expand every message into display lines, including a trailing blank line. */
export function buildChatLines(
  messages: ChatMessage[],
  width: number,
  traceExpanded: boolean,
): DisplayLine[] {
  const lines: DisplayLine[] = [];
  messages.forEach((message, messageIndex) => {
    // Include the position so a duplicate or reused id can never collide.
    const key = `m${messageIndex}-${message.id}`;
    if (message.kind === "trace") {
      lines.push(
        ...traceLines(
          message.steps ?? [],
          message.collapsedSummary ?? "",
          traceExpanded,
          width,
          key,
        ),
      );
      lines.push({ key: `${key}:gap`, text: "", tone: "text" });
      return;
    }
    if (message.kind === "tool" || message.kind === "tool-result") {
      const isCall = message.kind === "tool";
      lines.push({
        key,
        text: `${isCall ? "▸ " : message.ok === false ? "✕ " : "✓ "}${message.text}`,
        tone: isCall ? "info" : message.ok === false ? "danger" : "ok",
        dim: !isCall,
      });
      return;
    }

    const label =
      message.role === "user"
        ? "你"
        : message.role === "system"
          ? "系统"
          : "Exhibit";
    const duration =
      message.duration === undefined ? "" : ` · ${message.duration.toFixed(1)}s`;
    lines.push({
      key: `${key}:label`,
      text: `${label}${duration}`,
      tone:
        message.role === "user"
          ? "info"
          : message.role === "system"
            ? "warn"
            : "text",
      bold: true,
    });
    if (message.role === "assistant") {
      lines.push(...markdownLines(message.text, width, key, "text"));
    } else if (message.kind === undefined || message.kind === "message") {
      const tone: LineTone = message.role === "user" ? "info" : "text";
      message.text.split("\n").forEach((raw, lineIndex) => {
        lines.push(
          ...prefixedLines(raw, width, "", tone, `${key}:l${lineIndex}`),
        );
      });
    }
    lines.push({ key: `${key}:gap`, text: "", tone: "text" });
  });
  return lines;
}

/** Select the visible line window measured from the newest line upward. */
export function selectVisibleLines(
  lines: DisplayLine[],
  height: number,
  offset: number,
): {
  lines: DisplayLine[];
  offset: number;
  canUp: boolean;
  canDown: boolean;
} {
  const size = Math.max(1, Math.floor(height));
  const maxOffset = Math.max(0, lines.length - size);
  const clamped = Math.max(0, Math.min(Math.floor(offset), maxOffset));
  const end = lines.length - clamped;
  const start = Math.max(0, end - size);
  return {
    lines: lines.slice(start, end),
    offset: clamped,
    canUp: start > 0,
    canDown: clamped > 0,
  };
}
