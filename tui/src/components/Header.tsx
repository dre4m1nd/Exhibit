import React from "react";
import { displayWidth, padTo } from "../text.js";
import { SLASH_COMMANDS, type SlashCommand } from "../commands.js";

interface HeaderProps {
  taskTitle: string;
  repoPath: string;
  version?: string;
}

const LOGO = [
  "  ███████╗██╗  ██╗",
  "  ██╔════╝╚██╗██╔╝",
  "  █████╗   ╚███╔╝ ",
  "  ██╔══╝   ██╔██╗ ",
  "  ███████╗██╔╝ ██╗",
  "  ╚══════╝╚═╝  ╚═╝",
];

const CAPABILITIES = [
  "四类审查：arch · audit · repo · git",
  "常驻聊天：流式 token / 思考 / 工具",
  "计划模式：只读分析与能力隔离",
  "会话分叉：历史与 undo 互不污染",
];

const QUICK_COMMANDS = ["/login", "/review", "/diff", "/model", "/provider", "/plan"];

/**
 * Build the Pi-inspired banner as plain text lines so it can be unit-tested
 * without an Ink renderer. Returns one entry per rendered line.
 */
export function buildBanner(args: {
  taskTitle: string;
  repoPath: string;
  version: string;
  /** Terminal width in cells; the banner never renders wider than this. */
  columns?: number;
}): string[] {
  const { taskTitle, repoPath, version, columns = 0 } = args;
  const logo = LOGO;
  // The model is deliberately absent: chat mode resolves it from the saved
  // credential, so the always-visible status bar is the only truthful place.
  const welcome = [
    "  终端架构与审查智能体",
    `  ${taskTitle}`,
    "",
    `  ${repoPath}`,
  ];
  const commandRows = QUICK_COMMANDS.map(
    (name) => SLASH_COMMANDS.find((command) => command.name === name),
  ).filter((command): command is SlashCommand => command !== undefined);

  // Widths are measured in terminal cells, not code points: a CJK glyph takes
  // two columns, so padding by string length leaves the frame ragged.
  const leftWidth = Math.max(
    ...logo.map(displayWidth),
    ...welcome.map(displayWidth),
  );
  const rightWidth = Math.max(
    ...commandRows.map(
      (command) => displayWidth(command.name) + 2 + displayWidth(command.description),
    ),
    ...CAPABILITIES.map(displayWidth),
  );
  // The frame costs six cells (`│ ` + `  ` + ` │`). When the terminal is
  // narrower than the natural banner, shrink the right column and let it clip
  // with an ellipsis instead of wrapping and breaking the frame.
  const frame = 6;
  const budget = columns > 0 ? Math.max(frame + 12, columns - 1) : leftWidth + rightWidth + frame;
  const rightMin = 12;
  let left = leftWidth;
  let right = rightWidth;
  // Shrink the right column first, then the left; anything that still does not
  // fit is clipped with an ellipsis rather than wrapped.
  const overflow = Math.max(0, left + right + frame - budget);
  const rightCut = Math.min(overflow, right - rightMin);
  right -= rightCut;
  left = Math.max(rightMin, left - (overflow - rightCut));

  const title = ` Exhibit v${version} `;
  const innerWidth = left + 3 + right;

  const renderRow = (leftText: string, rightText: string): string =>
    `│ ${padTo(leftText, left)}  ${padTo(rightText, right)} │`;

  const rows = Math.max(logo.length, welcome.length);
  const body: string[] = [];
  for (let index = 0; index < rows; index += 1) {
    const logoLine = logo[index] ?? "";
    const welcomeLine = welcome[index] ?? "";
    body.push(renderRow(logoLine, welcomeLine));
  }
  body.push(renderRow("", "  命令"));
  commandRows.forEach((command) => {
    body.push(renderRow("", `${command.name}  ${command.description}`));
  });
  body.push(`│ ${" ".repeat(left)}  ${"─".repeat(right)} │`);
  body.push(renderRow("", "  Capabilities"));
  CAPABILITIES.forEach((line) => {
    body.push(renderRow("", `  ${line}`));
  });

  // Every row must be the same number of cells wide: the frame is one cell of
  // padding on each side plus the two content columns.
  const titleRow = `╭${title}${"─".repeat(innerWidth + 1 - displayWidth(title))}╮`;
  const bottom = `╰${"─".repeat(innerWidth + 1)}╯`;
  return [titleRow, ...body, bottom];
}
