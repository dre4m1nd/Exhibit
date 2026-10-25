import React from "react";
import { Box, Text } from "ink";
import { theme, SYMBOLS } from "../theme.js";

interface StatusBarProps {
  phase: string;
  detail: string;
  running: boolean;
  elapsedMs: number;
}

const PHASE_LABEL: Record<string, string> = {
  scanning: "准备",
  thinking: "推理",
  tool: "工具",
  writing: "成稿",
};

/** One-line status strip with a spinner glyph while the agent works. */
export function StatusBar({ phase, detail, running, elapsedMs }: StatusBarProps) {
  const seconds = (elapsedMs / 1000).toFixed(1);
  const label = PHASE_LABEL[phase] ?? phase;
  const glyph = running ? "◐" : SYMBOLS.ok;
  const color = running ? theme.accent : theme.muted;
  return (
    <Box borderStyle="round" borderColor={running ? theme.accent : theme.border} paddingX={1}>
      <Text color={color}>{glyph}</Text>
      <Text color={theme.muted}> {label} </Text>
      <Text color={theme.text}>{detail || "…"}</Text>
      <Box flexGrow={1} />
      <Text color={theme.muted}>{seconds}s</Text>
    </Box>
  );
}
