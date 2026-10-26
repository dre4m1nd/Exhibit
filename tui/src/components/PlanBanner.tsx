import React from "react";
import { Box, Text } from "ink";
import { theme } from "../theme.js";

export function PlanBanner({ active }: { active: boolean }) {
  if (!active) return null;
  return (
    <Box borderStyle="round" borderColor={theme.warn} paddingX={1}>
      <Text color={theme.warn} bold>
        PLAN{" "}
      </Text>
      <Text color={theme.muted}>只读分析模式 · /plan 退出后才能修改文件</Text>
    </Box>
  );
}
