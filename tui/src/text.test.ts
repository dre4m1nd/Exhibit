import { describe, expect, it } from "vitest";
import { displayWidth, padTo, truncate, truncateLeft } from "./text.js";

describe("truncate", () => {
  it("leaves short text untouched", () => {
    expect(truncate("abc", 10)).toBe("abc");
  });

  it("clips to the budget and marks the cut with an ellipsis", () => {
    const clipped = truncate("auto/dots-3-note-preview:free", 20);
    expect(displayWidth(clipped)).toBeLessThanOrEqual(20);
    expect(clipped.endsWith("…")).toBe(true);
  });

  it("counts CJK glyphs as two cells", () => {
    const clipped = truncate("架构审查报告草稿", 7);
    expect(displayWidth(clipped)).toBeLessThanOrEqual(7);
    expect(clipped).toBe("架构审…");
  });
});

describe("truncateLeft", () => {
  it("keeps the tail so a caret stays visible", () => {
    expect(truncateLeft("http://127.0.0.1:3425/v1", 12)).toBe("…0.1:3425/v1");
  });

  it("leaves short text untouched", () => {
    expect(truncateLeft("short", 20)).toBe("short");
  });
});

describe("padTo", () => {
  it("pads to an exact cell width", () => {
    expect(padTo("/status", 11)).toBe("/status    ");
    expect(displayWidth(padTo("/provider", 11))).toBe(11);
  });

  it("aligns CJK labels on the same column boundary", () => {
    expect(displayWidth(padTo("/review", 11))).toBe(displayWidth(padTo("/init", 11)));
  });

  it("clips instead of overflowing", () => {
    expect(displayWidth(padTo("a-very-long-command", 8))).toBe(8);
  });
});
