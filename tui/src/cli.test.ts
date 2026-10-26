import path from "node:path";
import { describe, expect, it } from "vitest";
import { parseCliArgs } from "./cli.js";

describe("launch arguments", () => {
  it("defaults to the current directory", () => {
    const cwd = path.resolve("C:/work/project");
    expect(parseCliArgs([], cwd)).toEqual({ repoPath: cwd, help: false });
  });

  it("accepts a positional path", () => {
    const cwd = path.resolve("C:/work/project");
    expect(parseCliArgs(["packages/api"], cwd).repoPath).toBe(
      path.resolve(cwd, "packages/api"),
    );
  });

  it("accepts PowerShell-style -Repo", () => {
    const cwd = path.resolve("C:/work/project");
    expect(parseCliArgs(["-Repo", "src"], cwd).repoPath).toBe(
      path.resolve(cwd, "src"),
    );
  });

  it("accepts --repo-path", () => {
    const cwd = path.resolve("C:/work/project");
    expect(parseCliArgs(["--repo-path", "src"], cwd).repoPath).toBe(
      path.resolve(cwd, "src"),
    );
  });

  it("recognizes help without requiring a path", () => {
    expect(parseCliArgs(["--help"], "C:/work/project").help).toBe(true);
  });

  it("rejects a missing path, duplicates, and unknown flags", () => {
    expect(() => parseCliArgs(["-Repo"], "C:/work/project")).toThrow(
      "requires a directory path",
    );
    expect(() => parseCliArgs(["a", "b"], "C:/work/project")).toThrow(
      "specified twice",
    );
    expect(() => parseCliArgs(["--wat"], "C:/work/project")).toThrow(
      "unknown option",
    );
  });
});
