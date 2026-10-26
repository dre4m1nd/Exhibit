import React from "react";
import { Box, Text } from "ink";
import { theme } from "../theme.js";
import { Markdown } from "./Markdown.js";
import {
  PALETTE_HEIGHT,
  suggestionsFor,
  windowAround,
} from "../commands.js";

export interface ChatMessage {
  id: number;
  role: "user" | "assistant" | "system";
  text: string;
  kind?: "message" | "tool" | "tool-result";
  ok?: boolean;
  duration?: number;
}

export function ChatView({
  messages,
  input,
  status,
  planMode,
  busy,
  selected = -1,
  elapsed = 0,
}: {
  messages: ChatMessage[];
  input: string;
  status: string;
  planMode: boolean;
  busy: boolean;
  selected?: number;
  elapsed?: number;
}) {
  const suggestions = suggestionsFor(input, planMode);
  const { start, end } = windowAround(selected, suggestions.length, PALETTE_HEIGHT);
  const shown = suggestions.slice(start, end);
  const choosingReview = suggestions.some((item) => item.kind === "review");
  return (
    <Box flexDirection="column">
      <Box flexDirection="column">
        {messages.length === 0 ? (
          <Text color={theme.muted}>输入问题，或键入 / 查看命令</Text>
        ) : (
          messages.map((message) => <Message key={message.id} message={message} />)
        )}
      </Box>
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
                <Text color={theme.accent}>{suggestion.label.padEnd(12)}</Text>
                {suggestion.description}
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
      <Box borderStyle="round" borderColor={planMode ? theme.warn : theme.accent} paddingX={1}>
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
      <Box borderStyle="round" borderColor={theme.border} paddingX={1}>
        <Text color={busy ? theme.accent : theme.muted}>
          {busy ? "◐" : "✓"}
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

function Message({ message }: { message: ChatMessage }) {
  if (message.kind === "tool" || message.kind === "tool-result") {
    const isCall = message.kind === "tool";
    const color = isCall
      ? theme.info
      : message.ok === false
        ? theme.danger
        : theme.ok;
    return (
      <Text color={color} dimColor={!isCall}>
        {isCall ? "▸ " : message.ok === false ? "✕ " : "✓ "}
        {message.text}
      </Text>
    );
  }
  const label = message.role === "user" ? "你" : message.role === "system" ? "系统" : "Exhibit";
  const color = message.role === "user" ? theme.info : message.role === "system" ? theme.warn : theme.text;
  return (
    <Box flexDirection="column" marginBottom={1}>
      <Text color={color} bold>
        {label}
        {message.duration !== undefined ? (
          <Text color={theme.muted}> · {message.duration.toFixed(1)}s</Text>
        ) : null}
      </Text>
      {message.role === "assistant" ? (
        <Markdown source={message.text} role={message.role} />
      ) : (
        <Text color={theme.text}>{message.text}</Text>
      )}
    </Box>
  );
}
