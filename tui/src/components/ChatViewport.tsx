import React from "react";
import { Box, Static, Text } from "ink";
import { padTo, truncate } from "../text.js";
import { theme } from "../theme.js";
import { useTerminalSize } from "../useTerminalSize.js";
import type { ChatMessage } from "./ChatView.js";
import {
  buildChatLines,
  buildLiveTraceLines,
  tailLines,
  type LineTone,
} from "../chatLines.js";
import type { TraceStep } from "../trace.js";
import {
  PALETTE_HEIGHT,
  windowAround,
  type Suggestion,
} from "../commands.js";

/** Chrome outside the message viewport: input, status and live trace. */
const CHROME_ROWS = 8;

/** Rows available to the streaming draft; `extraRows` covers the palette. */
export function viewportHeight(rows: number, extraRows = 0): number {
  if (!Number.isFinite(rows) || rows <= 0) return 5;
  return Math.max(3, rows - CHROME_ROWS - Math.max(0, extraRows));
}

/** Rows available to an expanded live trace while keeping the viewport visible. */
export function liveTraceRows(rows: number, extraRows = 0): number {
  if (!Number.isFinite(rows) || rows <= 0) return 1;
  return Math.max(1, Math.floor(rows) - CHROME_ROWS - Math.max(0, extraRows) - 3);
}

const TONE_COLOR: Record<LineTone, string> = {
  accent: theme.accent,
  text: theme.text,
  muted: theme.muted,
  info: theme.info,
  ok: theme.ok,
  danger: theme.dangerText,
  warn: theme.warn,
  border: theme.border,
};

export function ChatViewport({
  messages,
  draft,
  input,
  status,
  planMode,
  busy,
  suggestions,
  selected = -1,
  elapsed = 0,
  traceExpanded = false,
  liveTrace = [],
  failed = false,
}: {
  messages: ChatMessage[];
  draft?: ChatMessage | null;
  input: string;
  status: string;
  planMode: boolean;
  busy: boolean;
  suggestions: Suggestion[];
  selected?: number;
  elapsed?: number;
  traceExpanded?: boolean;
  liveTrace?: TraceStep[];
  failed?: boolean;
}) {
  const { start, end } = windowAround(selected, suggestions.length, PALETTE_HEIGHT);
  const shown = suggestions.slice(start, end);
  const choosingReview = suggestions.some((item) => item.kind === "review");
  const size = useTerminalSize();

  const contentWidth = Math.max(20, size.columns - 2);
  const paletteRows = shown.length === 0 ? 0 : shown.length + 1;
  const liveRows = liveTraceRows(size.rows, paletteRows);
  // Memoised so a per-token draft update does not rebuild the live trace, and
  // a per-second elapsed tick does not rebuild the draft.
  const liveLines = React.useMemo(
    () => tailLines(
      buildLiveTraceLines(liveTrace, contentWidth, traceExpanded),
      liveRows,
    ),
    [contentWidth, liveRows, liveTrace, traceExpanded],
  );
  const draftLines = React.useMemo(
    () => (draft ? buildChatLines([draft], contentWidth, traceExpanded) : []),
    [contentWidth, draft, traceExpanded],
  );
  const draftRows = viewportHeight(
    size.rows,
    paletteRows + liveLines.length + (planMode ? 3 : 0),
  );
  const visibleDraft = draftLines.slice(-draftRows);
  const visibleMessages = React.useMemo(
    () =>
      messages.map((message) => ({
        message,
        lines: buildChatLines([message], contentWidth, traceExpanded),
      })),
    [contentWidth, messages, traceExpanded],
  );

  return (
    <Box flexDirection="column">
      <Static items={visibleMessages}>
        {({ message, lines }) => (
          <Box key={message.id} flexDirection="column">
            {lines.map((line) => (
              <Text
                key={line.key}
                color={TONE_COLOR[line.tone]}
                bold={line.bold}
                dimColor={line.dim}
              >
                {line.text || " "}
              </Text>
            ))}
          </Box>
        )}
      </Static>
      {visibleDraft.length > 0 ? (
        <Box flexDirection="column">
          {visibleDraft.map((line) => (
            <Text
              key={line.key}
              color={TONE_COLOR[line.tone]}
              bold={line.bold}
              dimColor={line.dim}
            >
              {line.text || " "}
            </Text>
          ))}
        </Box>
      ) : null}
      {messages.length === 0 && visibleDraft.length === 0 ? (
        <Text color={theme.muted}>输入问题，或键入 / 查看命令</Text>
      ) : null}
      {shown.length > 0 ? (
        <Box flexDirection="column">
          {shown.map((suggestion, offset) => {
            const active = start + offset === selected;
            return (
              <Text
                key={`${suggestion.kind}-${suggestion.label}`}
                color={active ? theme.accent : theme.muted}
              >
                <Text color={active ? theme.accent : theme.muted}>
                  {active ? "❯ " : "  "}
                </Text>
                <Text color={theme.accent}>{padTo(suggestion.label, 11)} </Text>
                {truncate(suggestion.description, contentWidth - 15)}
              </Text>
            );
          })}
          <Text color={theme.muted}>
            {choosingReview
              ? "↑↓ 选择审查类型 · Tab 补全 · Enter 执行"
              : "↑↓ 选择 · Tab 补全 · Enter 执行"}
          </Text>
        </Box>
      ) : null}
      {liveLines.length > 0 ? (
        <Box flexDirection="column" height={liveLines.length} overflow="hidden">
          {liveLines.map((line) => (
            <Text
              key={line.key}
              color={TONE_COLOR[line.tone]}
              bold={line.bold}
              dimColor={line.dim}
            >
              {line.text || " "}
            </Text>
          ))}
        </Box>
      ) : null}
      <Box
        borderStyle="round"
        borderColor={planMode ? theme.warn : theme.accent}
        paddingX={1}
      >
        <Text color={planMode ? theme.warn : theme.accent} bold>
          {planMode ? "PLAN" : busy ? "◐" : "›"}{" "}
        </Text>
        {input ? (
          <Text color={theme.text}>
            {input}
            <Text color={theme.accent}>▌</Text>
          </Text>
        ) : (
          <Text color={theme.muted}>
            {busy ? "等待回复…" : "输入消息"}▌
          </Text>
        )}
      </Box>
      <Box
        borderStyle="round"
        borderColor={failed ? theme.danger : theme.border}
        paddingX={1}
      >
        <Text color={failed ? theme.danger : busy ? theme.accent : theme.muted}>
          {failed ? "✗" : busy ? "◐" : "✓"}
        </Text>
        <Text color={theme.text}> {status}</Text>
        <Box flexGrow={1} />
        {busy || elapsed > 0 ? (
          <Text color={theme.muted}>
            {busy ? "运行中 " : "用时 "}
            {elapsed.toFixed(1)}s
          </Text>
        ) : null}
      </Box>
    </Box>
  );
}
