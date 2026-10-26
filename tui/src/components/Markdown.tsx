import React from "react";
import { Box, Text } from "ink";
import { theme } from "../theme.js";

interface MarkdownProps {
  source: string;
  role?: "user" | "assistant" | "system";
}

/** Block-level units produced by the lightweight terminal markdown parser. */
type Block =
  | { kind: "heading"; level: number; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "code"; text: string }
  | { kind: "quote"; text: string }
  | { kind: "bullet"; text: string }
  | { kind: "rule" };

const HEADING_PREFIX: Record<number, string> = { 1: "▌", 2: "▌", 3: "•" };

/** Parse a small, review-friendly subset of Markdown into render blocks. */
export function parseMarkdown(source: string): Block[] {
  const blocks: Block[] = [];
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  let code: string[] | null = null;
  let paragraph: string[] = [];

  const flushParagraph = () => {
    if (paragraph.length > 0) {
      blocks.push({ kind: "paragraph", text: paragraph.join(" ").trim() });
      paragraph = [];
    }
  };

  for (const raw of lines) {
    const line = raw.replace(/\s+$/, "");
    const fence = line.match(/^```(.*)$/);
    if (fence) {
      if (code === null) {
        flushParagraph();
        code = [];
      } else {
        blocks.push({ kind: "code", text: code.join("\n") });
        code = null;
      }
      continue;
    }
    if (code !== null) {
      code.push(line);
      continue;
    }
    if (line.trim() === "") {
      flushParagraph();
      continue;
    }
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(line.trim())) {
      flushParagraph();
      blocks.push({ kind: "rule" });
      continue;
    }
    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading && heading[1] && heading[2] !== undefined) {
      flushParagraph();
      blocks.push({
        kind: "heading",
        level: heading[1].length,
        text: heading[2].trim(),
      });
      continue;
    }
    const bullet = line.match(/^\s*[-*]\s+(.*)$/);
    if (bullet && bullet[1] !== undefined) {
      flushParagraph();
      blocks.push({ kind: "bullet", text: bullet[1].trim() });
      continue;
    }
    const quote = line.match(/^>\s?(.*)$/);
    if (quote && quote[1] !== undefined) {
      flushParagraph();
      blocks.push({ kind: "quote", text: quote[1].trim() });
      continue;
    }
    paragraph.push(line.trim());
  }
  flushParagraph();
  if (code !== null) blocks.push({ kind: "code", text: code.join("\n") });
  return blocks;
}

/** Render inline emphasis and inline code spans within a single line. */
function renderInline(text: string, color: string) {
  const tokens = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean);
  return tokens.map((token, index) => {
    if (token.startsWith("**") && token.endsWith("**")) {
      return (
        <Text key={index} bold color={color}>
          {token.slice(2, -2)}
        </Text>
      );
    }
    if (token.startsWith("`") && token.endsWith("`")) {
      return (
        <Text key={index} color={theme.accent}>
          {token.slice(1, -1)}
        </Text>
      );
    }
    return <Text key={index} color={color}>{token}</Text>;
  });
}

/** Render Markdown using terminal primitives; no external dependencies. */
export function Markdown({ source, role = "assistant" }: MarkdownProps) {
  const color =
    role === "user" ? theme.info : role === "system" ? theme.warn : theme.text;
  const blocks = parseMarkdown(source);
  return (
    <Box flexDirection="column">
      {blocks.map((block, index) => {
        switch (block.kind) {
          case "heading": {
            const prefix = HEADING_PREFIX[block.level] ?? "•";
            return (
              <Text key={index} color={theme.accent} bold>
                {prefix} {block.text}
              </Text>
            );
          }
          case "rule":
            return <Text key={index} color={theme.border}>{`─`.repeat(40)}</Text>;
          case "quote":
            return (
              <Box key={index}>
                <Text color={theme.muted}>▌ </Text>
                <Text color={theme.muted} dimColor>
                  {block.text}
                </Text>
              </Box>
            );
          case "bullet":
            return (
              <Box key={index}>
                <Text color={theme.accent}>• </Text>
                <Text color={color}>{renderInline(block.text, color)}</Text>
              </Box>
            );
          case "code":
            return (
              <Box key={index} flexDirection="column" paddingX={1}>
                {block.text.split("\n").map((codeLine, lineIndex) => (
                  <Text key={lineIndex} color={theme.ok}>
                    {codeLine || " "}
                  </Text>
                ))}
              </Box>
            );
          default:
            return (
              <Text key={index} color={color} wrap="wrap">
                {renderInline(block.text, color)}
              </Text>
            );
        }
      })}
    </Box>
  );
}
