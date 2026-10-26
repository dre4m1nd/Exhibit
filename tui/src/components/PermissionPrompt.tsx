import React from "react";
import { Box, Text, useInput } from "ink";
import { theme } from "../theme.js";

/** How the user resolved a pending write. */
export type PermissionScope = "once" | "reject" | "session";

export function PermissionPrompt({
  path,
  action,
  summary,
  trusted = false,
  onDecision,
}: {
  path: string;
  action: string;
  summary: string;
  trusted?: boolean;
  onDecision: (scope: PermissionScope) => void;
}) {
  useInput((input, key) => {
    if (key.ctrl && input === "c") {
      onDecision("reject");
      return;
    }
    if (input === "y" || key.return) onDecision("once");
    else if (input === "s") onDecision("session");
    else if (input === "n" || key.escape) onDecision("reject");
  });

  return (
    <Box flexDirection="column" borderStyle="double" borderColor={theme.warn} paddingX={1}>
      <Text color={theme.warn} bold>
        文件修改需要确认
      </Text>
      <Text color={theme.text}>
        {action} {path}
      </Text>
      <Text color={theme.muted}>{summary}</Text>
      <Text color={theme.muted}>
        按 y 允许一次 · s 本会话允许 · n 拒绝
      </Text>
      {trusted ? <Text color={theme.accent}>本会话已开启自动允许，后续写入不再询问</Text> : null}
    </Box>
  );
}
