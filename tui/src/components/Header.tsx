import React from "react";
import { Box, Text } from "ink";
import { theme } from "../theme.js";
import { SLASH_COMMANDS, type SlashCommand } from "../commands.js";

interface HeaderProps {
  taskTitle: string;
  repoPath: string;
  model: string;
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
  model: string;
  version: string;
}): string[] {
  const { taskTitle, repoPath, model, version } = args;
  const logo = LOGO;
  const welcome = [
    "  终端架构与审查智能体",
    `  ${taskTitle}`,
    "",
    `  ${model}`,
    `  ${repoPath}`,
  ];
  const commandRows = QUICK_COMMANDS.map(
    (name) => SLASH_COMMANDS.find((command) => command.name === name),
  ).filter((command): command is SlashCommand => command !== undefined);

  const leftWidth = Math.max(
    ...logo.map((line) => line.length),
    ...welcome.map((line) => line.length),
  );
  const rightWidth = Math.max(
    ...commandRows.map((command) => command.name.length + 2 + command.description.length),
    ...CAPABILITIES.map((line) => line.length),
  );
  const innerWidth = leftWidth + 3 + rightWidth;
  const title = ` Exhibit v${version} `;

  const renderRow = (left: string, right: string): string => {
    const leftPadded = (left + " ".repeat(leftWidth)).slice(0, leftWidth);
    const rightPadded = (right + " ".repeat(rightWidth)).slice(0, rightWidth);
    return `│ ${leftPadded}  ${rightPadded} │`;
  };

  const rows = Math.max(logo.length, welcome.length);
  const body: string[] = [];
  for (let index = 0; index < rows; index += 1) {
    const left = logo[index] ?? " ".repeat(leftWidth);
    const right = welcome[index] ?? "";
    body.push(renderRow(left, right));
  }
  body.push(renderRow("", "  命令"));
  commandRows.forEach((command) => {
    const right = `${command.name}  ${command.description}`.slice(0, rightWidth);
    body.push(renderRow("", right));
  });
  body.push(`│${" ".repeat(leftWidth)}  ${"─".repeat(rightWidth)}│`);
  body.push(renderRow("", "  Capabilities"));
  CAPABILITIES.forEach((line) => {
    body.push(renderRow("", `  ${line}`.slice(0, rightWidth)));
  });

  const titleRow = `╭${title}${"─".repeat(innerWidth - title.length + 2)}╮`;
  const bottom = `╰${"─".repeat(innerWidth + 2)}╯`;
  return [titleRow, ...body, bottom];
}

/** The one-time branded banner written into terminal history. */
export function Header({ taskTitle, repoPath, model, version = "0.1.0" }: HeaderProps) {
  const lines = buildBanner({ taskTitle, repoPath, model, version });
  return (
    <Box flexDirection="column">
      {lines.map((line, index) => (
        <Text key={index} color={theme.border}>
          {line}
        </Text>
      ))}
      <Box height={1} />
    </Box>
  );
}
