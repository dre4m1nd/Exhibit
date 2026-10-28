import { describe, expect, it } from "vitest";
import { liveTraceRows, viewportHeight } from "./ChatViewport.js";

describe("viewportHeight", () => {
  it("never goes below the 3-row floor", () => {
    expect(viewportHeight(8)).toBe(3);
  });

  it("subtracts fixed chrome on a normal terminal", () => {
    expect(viewportHeight(40)).toBe(32);
  });

  it("reserves rows for the palette, banner and live trace", () => {
    expect(viewportHeight(40, 7)).toBe(25);
  });

  it("ignores non-finite values", () => {
    expect(viewportHeight(Number.NaN)).toBe(5);
  });

  it("reserves a bounded area for the expanded live trace", () => {
    expect(liveTraceRows(40)).toBe(29);
    expect(liveTraceRows(10)).toBe(1);
    expect(liveTraceRows(Number.NaN)).toBe(1);
  });
});
