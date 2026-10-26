import { describe, expect, it } from "vitest";
import {
  availableCommands,
  moveSelection,
  parseCommandArgs,
  SLASH_COMMANDS,
  suggestionsFor,
  TAKES_ARGUMENTS,
  windowAround,
} from "./commands.js";

describe("slash commands", () => {
  it("has a one-line description for every command", () => {
    expect(SLASH_COMMANDS.every((command) => command.description.length > 0)).toBe(true);
  });

  it("does not expose a /help command", () => {
    expect(SLASH_COMMANDS.some((command) => command.name === "/help")).toBe(false);
  });

  it("matches the typed slash prefix", () => {
    expect(availableCommands("/lo", false).map((command) => command.name)).toEqual([
      "/login",
      "/logout",
    ]);
    expect(availableCommands("/pl", false).map((command) => command.name)).toEqual([
      "/plan",
    ]);
  });

  it("hides suggestions for ordinary chat and empty input", () => {
    expect(availableCommands("", false)).toEqual([]);
    expect(availableCommands("hello", false)).toEqual([]);
    expect(availableCommands("/login openai", false)).toEqual([]);
  });

  it("offers review types after /review and filters them by prefix", () => {
    expect(suggestionsFor("/review ", false).map((item) => item.label)).toEqual([
      "arch",
      "audit",
      "repo",
      "git",
    ]);
    expect(suggestionsFor("/review au", false).map((item) => item.label)).toEqual([
      "audit",
    ]);
    expect(suggestionsFor("/review audit,", false)).toEqual([]);
  });

  it("keeps ordinary command suggestions and their insert/execute metadata", () => {
    expect(suggestionsFor("/lo", false).map((item) => item.label)).toEqual([
      "/login",
      "/logout",
    ]);
    expect(suggestionsFor("/review", false)[0]).toMatchObject({
      insert: "/review",
      takesArguments: true,
    });
    expect(suggestionsFor("/status", false)[0]?.execute).toBe("/status");
  });

  it("keeps the full command object, including requiresConfirm", () => {
    const logout = availableCommands("/logout", false)[0];
    expect(logout?.requiresConfirm).toBe(true);
  });

  it("marks only /review and /diff as taking arguments", () => {
    expect([...TAKES_ARGUMENTS]).toEqual(["/review", "/diff"]);
  });

  it("parses review tasks and diff ranges", () => {
    expect(parseCommandArgs("/review", ["audit"])).toEqual({ task: "audit" });
    expect(parseCommandArgs("/review", ["审查这个项目的架构"])).toEqual({
      task: "审查这个项目的架构",
    });
    expect(
      parseCommandArgs("/review", ["审查", "这个项目的", "架构"]),
    ).toEqual({ task: "审查 这个项目的 架构" });
    expect(parseCommandArgs("/review", ["audit,git"])).toEqual({
      task: "audit,git",
    });
    expect(parseCommandArgs("/diff", ["--range", "HEAD~2..HEAD"])).toEqual({
      commit_range: "HEAD~2..HEAD",
    });
    expect(
      parseCommandArgs("/review", ["git", "--branch", "feature/review"]),
    ).toEqual({ task: "git", branch: "feature/review" });
  });

  it("hides /undo while plan mode is active", () => {
    expect(availableCommands("/un", true)).toEqual([]);
    expect(availableCommands("/un", false).map((item) => item.name)).toEqual([
      "/undo",
    ]);
  });

  it("moves the selection in a ring", () => {
    expect(moveSelection(0, 1, 3)).toBe(1);
    expect(moveSelection(2, 1, 3)).toBe(0);
    expect(moveSelection(0, -1, 3)).toBe(2);
    expect(moveSelection(-1, 1, 3)).toBe(1);
    expect(moveSelection(0, 1, 0)).toBe(-1);
  });

  it("keeps the highlighted row inside the window", () => {
    expect(windowAround(0, 16, 6)).toEqual({ start: 0, end: 6 });
    expect(windowAround(8, 16, 6)).toEqual({ start: 5, end: 11 });
    expect(windowAround(15, 16, 6)).toEqual({ start: 10, end: 16 });
    expect(windowAround(0, 2, 6)).toEqual({ start: 0, end: 2 });
    expect(windowAround(0, 0, 6)).toEqual({ start: 0, end: 0 });
  });

  it("requires an explicit confirmation for destructive commands", () => {
    expect(parseCommandArgs("/clear", [])).toEqual({ confirm: false });
    expect(parseCommandArgs("/logout", [])).toEqual({ confirm: false });
    expect(parseCommandArgs("/clear", ["--confirm"])).toEqual({ confirm: true });
    expect(parseCommandArgs("/logout", ["--confirm"])).toEqual({ confirm: true });
    expect(parseCommandArgs("/status", [])).toEqual({});
  });
});
