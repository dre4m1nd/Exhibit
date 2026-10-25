import React from "react";
import { Box, Text, useInput } from "ink";
import { useState } from "react";
import { theme, SYMBOLS } from "../theme.js";

interface ReportViewProps {
  markdown: string;
  onSave: () => void;
  onQuit: () => void;
}

/** Renders the final report, scrolling with the arrow keys. */
export function ReportView({ markdown, onSave, onQuit }: ReportViewProps) {
  const [offset, setOffset] = useState(0);
  const lines = markdown.split("\n");
  const pageSize = 20;

  useInput((input, key) => {
    if (key.downArrow || input === "j") {
      setOffset((value) => Math.min(value + 1, Math.max(0, lines.length - pageSize)));
    } else if (key.upArrow || input === "k") {
      setOffset((value) => Math.max(0, value - 1));
    } else if (key.pageDown) {
      setOffset((value) => Math.min(value + pageSize, Math.max(0, lines.length - pageSize)));
    } else if (key.pageUp) {
      setOffset((value) => Math.max(0, value - pageSize));
    } else if (input === "s") {
      onSave();
    } else if (input === "q" || key.escape) {
      onQuit();
    }
  });

  const window = lines.slice(offset, offset + pageSize);

  return (
    <Box flexDirection="column" borderStyle="round" borderColor={theme.accent} paddingX={1}>
      <Text color={theme.accent} bold>
        {SYMBOLS.report} 报告
        <Text color={theme.muted}>
          {"  "}
          {offset + 1}-{Math.min(offset + pageSize, lines.length)} / {lines.length} 行
          {"  "}↑↓ 滚动 · s 保存 · q 退出
        </Text>
      </Text>
      <Box flexDirection="column" height={pageSize + 1}>
        {window.map((line, index) => (
          <ReportLine key={`${offset + index}`} line={line} />
        ))}
      </Box>
    </Box>
  );
}

function ReportLine({ line }: { line: string }) {
  const common = { wrap: "truncate-end" as const };
  if (line.startsWith("# ")) {
    return <Text color={theme.accent} bold {...common}>{line}</Text>;
  }
  if (line.startsWith("## ")) {
    return <Text color={theme.accent} bold {...common}>{line}</Text>;
  }
  if (line.startsWith("### ")) {
    return <Text color={theme.info} bold {...common}>{line}</Text>;
  }
  if (line.startsWith("- ") || line.startsWith("* ")) {
    return <Text color={theme.text} {...common}>{line}</Text>;
  }
  if (/^\s*(高|中|低)严重度/.test(line)) {
    return <Text color={theme.danger} bold {...common}>{line}</Text>;
  }
  return <Text color={theme.text} {...common}>{line}</Text>;
}
