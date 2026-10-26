import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { buildAgentArgs, findInstallRoot, resolvePython } from "./bridge.js";

const originalHome = process.env.EXHIBIT_HOME;
const originalPython = process.env.EXHIBIT_PYTHON;

afterEach(() => {
  if (originalHome === undefined) delete process.env.EXHIBIT_HOME;
  else process.env.EXHIBIT_HOME = originalHome;
  if (originalPython === undefined) delete process.env.EXHIBIT_PYTHON;
  else process.env.EXHIBIT_PYTHON = originalPython;
});

describe("installation paths", () => {
  it("finds Exhibit's root instead of the caller's working directory", () => {
    delete process.env.EXHIBIT_HOME;
    const root = findInstallRoot();
    expect(path.join(root, "agent", "app.py")).toContain("agent");
  });

  it("honors EXHIBIT_HOME for nonstandard installations", () => {
    process.env.EXHIBIT_HOME = path.resolve("C:/tools/exhibit");
    expect(findInstallRoot()).toBe(path.resolve("C:/tools/exhibit"));
  });

  it("resolves the venv Python under the installation root", () => {
    delete process.env.EXHIBIT_PYTHON;
    const python = resolvePython(path.resolve("C:/tools/exhibit"));
    expect(python).toContain(path.join("C:/tools/exhibit", ".venv"));
  });

  it("passes the requested repository to the Python agent", () => {
    const target = path.resolve("C:/work/another-project");
    expect(buildAgentArgs(target)).toEqual([
      "-u",
      "-m",
      "agent.app",
      "--repo-path",
      target,
    ]);
  });
});
