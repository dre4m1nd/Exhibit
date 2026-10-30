import { describe, expect, it } from "vitest";
import { displayWidth } from "../chatLines.js";
import { buildBanner } from "./Header.js";

describe("buildBanner", () => {
  const lines = buildBanner({
    taskTitle: "Exhibit Chat",
    repoPath: "D:\\Code\\Exhibit",
    version: "1.2.3",
  });

  it("wraps every line in a box with matching corners", () => {
    expect(lines[0]).toMatch(/^╭.*╮$/);
    expect(lines[lines.length - 1]).toMatch(/^╰.*╯$/);
    for (const line of lines) {
      if (line.startsWith("╭") || line.startsWith("╰")) continue;
      expect(line.startsWith("│")).toBe(true);
      expect(line.endsWith("│")).toBe(true);
    }
  });

  it("keeps every row the same cell width so the frame stays straight", () => {
    const widths = new Set(lines.map(displayWidth));
    expect([...widths]).toHaveLength(1);
  });

  it("embeds the version in the title row", () => {
    expect(lines[0]).toContain("Exhibit v1.2.3");
  });

  it("renders the wordmark and the repository path", () => {
    const text = lines.join("\n");
    expect(text).toContain("██");
    expect(text).toContain("D:\\Code\\Exhibit");
  });

  it("lists the quick commands and a capabilities block", () => {
    const text = lines.join("\n");
    expect(text).toContain("/login");
    expect(text).toContain("/review");
    expect(text).toContain("Capabilities");
    expect(text).toContain("四类审查");
  });
});
