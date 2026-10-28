import { describe, expect, it } from "vitest";
import { sessionStatus } from "./App.js";

describe("sessionStatus", () => {
  it("names the session when nothing else is known", () => {
    expect(sessionStatus({ session: "main" })).toBe("会话 main");
  });

  it("shows the provider and model the agent will actually call", () => {
    expect(
      sessionStatus({
        session: "main",
        provider: "custom",
        model: "group/master",
      }),
    ).toBe("会话 main · custom · group/master");
  });

  it("marks plan mode next to the session name", () => {
    expect(
      sessionStatus({ session: "fork-01", mode: "plan", provider: "deepseek" }),
    ).toBe("会话 fork-01 · plan · deepseek");
  });

  it("keeps agent mode implicit and ignores missing fields", () => {
    expect(sessionStatus({ session: "main", mode: "agent", model: "" })).toBe(
      "会话 main",
    );
  });
});
