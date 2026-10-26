import { describe, expect, it } from "vitest";
import { parseMarkdown } from "./Markdown.js";

describe("parseMarkdown", () => {
  it("splits headings, paragraphs, and bullets", () => {
    const blocks = parseMarkdown(
      "# 标题\n正文一行\n\n- 第一项\n- 第二项\n\n## 小节\ntail",
    );
    expect(blocks[0]).toEqual({ kind: "heading", level: 1, text: "标题" });
    expect(blocks[1]).toEqual({ kind: "paragraph", text: "正文一行" });
    expect(blocks[2]).toEqual({ kind: "bullet", text: "第一项" });
    expect(blocks[3]).toEqual({ kind: "bullet", text: "第二项" });
    expect(blocks[4]).toEqual({ kind: "heading", level: 2, text: "小节" });
    expect(blocks[5]).toEqual({ kind: "paragraph", text: "tail" });
  });

  it("captures fenced code blocks verbatim", () => {
    const blocks = parseMarkdown("```java\nint x = 1;\n```");
    expect(blocks).toEqual([{ kind: "code", text: "int x = 1;" }]);
  });

  it("keeps blockquote and rule markers", () => {
    const blocks = parseMarkdown("> 注意\n\n---");
    expect(blocks[0]).toEqual({ kind: "quote", text: "注意" });
    expect(blocks[1]).toEqual({ kind: "rule" });
  });

  it("folds soft-wrapped lines into one paragraph", () => {
    const blocks = parseMarkdown("line one\nline two");
    expect(blocks).toEqual([
      { kind: "paragraph", text: "line one line two" },
    ]);
  });
});
