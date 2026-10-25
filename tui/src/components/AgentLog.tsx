import React from "react";
import { Box, Text } from "ink";
import { theme, SYMBOLS } from "../theme.js";

export interface LogEntry {
  id: number;
  kind: "status" | "tool" | "result" | "token" | "error";
  text: string;
}

interface AgentLogProps {
  entries: LogEntry[];
  height?: number;
}

/** The scrolling stream of agent activity. */
export function AgentLog({ entries, height = 14 }: AgentLogProps) {
  const visible = entries.slice(-height);
  return (
    <Box flexDirection="column" borderStyle="round" borderColor={theme.border} paddingX={1} height={height + 2}>
      {visible.length === 0 ? (
        <Text color={theme.muted}>等待智能体开始…</Text>
      ) : (
        visible.map((entry) => (
          <LogLine key={entry.id} entry={entry} />
        ))
      )}
    </Box>
  );
}

function LogLine({ entry }: { entry: LogEntry }) {
  const text = oneLine(entry.text);
  switch (entry.kind) {
    case "tool":
      return (
        <Text color={theme.info} wrap="truncate-end">
          {SYMBOLS.tool} {text}
        </Text>
      );
    case "result":
      return (
        <Text color={theme.ok} dimColor wrap="truncate-end">
          {SYMBOLS.bullet} {text}
        </Text>
      );
    case "error":
      return (
        <Text color={theme.danger} wrap="truncate-end">
          {SYMBOLS.fail} {text}
        </Text>
      );
    case "token":
      return (
        <Text color={theme.muted} wrap="truncate-end">
          {text}
        </Text>
      );
    default:
      return (
        <Text color={theme.accentDim} wrap="truncate-end">
          {text}
        </Text>
      );
  }
}

/** Collapse whitespace so a log entry always occupies exactly one row. */
function oneLine(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}
