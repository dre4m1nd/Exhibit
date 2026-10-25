import React from "react";
import { Box, Text } from "ink";
import { theme } from "../theme.js";

interface HeaderProps {
  taskTitle: string;
  repoPath: string;
  model: string;
}

/** The branded header shown while a task runs. */
export function Header({ taskTitle, repoPath, model }: HeaderProps) {
  return (
    <Box
      flexDirection="column"
      borderStyle="round"
      borderColor={theme.accent}
      paddingX={2}
      paddingY={0}
    >
      <Text color={theme.accent} bold>
        EXHIBIT
        <Text color={theme.muted}> · 终端架构与审查智能体</Text>
      </Text>
      <Text color={theme.text}>
        {taskTitle}
        <Text color={theme.muted}>
          {"  "}仓库 {repoPath}
          {"  "}模型 {model}
        </Text>
      </Text>
    </Box>
  );
}
