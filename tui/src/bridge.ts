/** Spawns the Python agent subprocess and forwards its protocol events. */

import { spawn, type ChildProcess } from "node:child_process";
import { existsSync, realpathSync } from "node:fs";
import path from "node:path";
import readline from "node:readline";
import { fileURLToPath } from "node:url";
import { parseLine } from "./protocol.js";
import type { AgentMessage } from "./protocol.js";

export interface BridgeOptions {
  repoPath: string;
  onMessage: (message: AgentMessage) => void;
  onError: (error: Error) => void;
  onExit?: (code: number | null) => void;
}

export interface AgentBridge {
  sendChat: (text: string) => void;
  sendCommand: (name: string, args?: Record<string, unknown>) => void;
  sendPermission: (
    requestId: string,
    approved: boolean,
    scope?: "once" | "session",
  ) => void;
  stop: () => void;
}

/** Locate Exhibit's installation root, independent of the target repository. */
export function findInstallRoot(): string {
  const override = process.env.EXHIBIT_HOME?.trim();
  if (override) return path.resolve(override);

  const entry = realpathSync(fileURLToPath(import.meta.url));
  let current = path.dirname(entry);
  while (true) {
    if (existsSync(path.join(current, "agent", "app.py"))) return current;
    const parent = path.dirname(current);
    if (parent === current) break;
    current = parent;
  }
  // Keep a deterministic fallback for a partially installed package.
  return path.resolve(path.dirname(entry), "..", "..");
}

/** Resolve the python interpreter of the project's virtualenv. */
export function resolvePython(repoRoot: string): string {
  if (process.env.EXHIBIT_PYTHON) return process.env.EXHIBIT_PYTHON;
  const isWin = process.platform === "win32";
  const venvPython = isWin
    ? path.join(repoRoot, ".venv", "Scripts", "python.exe")
    : path.join(repoRoot, ".venv", "bin", "python");
  return venvPython;
}

/** Arguments passed to the Python module, including the target repository. */
export function buildAgentArgs(repoPath: string): string[] {
  return ["-u", "-m", "agent.app", "--repo-path", path.resolve(repoPath)];
}

/**
 * Kill the interpreter and any launcher child it created.
 *
 * On Windows a virtualenv's `python.exe` can start the real interpreter as a
 * child, so `ChildProcess.kill()` alone leaves that grandchild alive. The
 * taskkill tree flag is only available on Windows, hence the platform branch.
 */
export function killProcessTree(child: ChildProcess): void {
  if (!child.pid) return;
  if (process.platform === "win32") {
    spawn("taskkill", ["/pid", String(child.pid), "/T", "/F"], {
      stdio: "ignore",
      windowsHide: true,
    }).on("error", () => child.kill());
    return;
  }
  child.kill("SIGTERM");
}

/** Start the agent and return the subprocess handle. */
function writeLine(child: ChildProcess, message: Record<string, unknown>): void {
  if (!child.stdin?.writable) return;
  child.stdin.write(`${JSON.stringify(message)}\n`);
}

/** Start one long-lived agent process for the whole conversation. */
export function startAgent(options: BridgeOptions): AgentBridge {
  const installRoot = findInstallRoot();
  const python = resolvePython(installRoot);
  const repoPath = path.resolve(options.repoPath);

  const child = spawn(
    python,
    buildAgentArgs(repoPath),
    {
      // The module lives in the install root; the reviewed directory is passed
      // explicitly so launching from another project cannot change imports.
      cwd: installRoot,
      stdio: ["pipe", "pipe", "pipe"],
      env: {
        ...process.env,
        EXHIBIT_REPO_ROOT: repoPath,
        PYTHONIOENCODING: "utf-8",
        PYTHONUNBUFFERED: "1",
      },
    },
  );

  const rl = readline.createInterface({ input: child.stdout });
  rl.on("line", (line: string) => {
    if (!line.trim()) return;
    const message = parseLine(line);
    if (message) options.onMessage(message);
  });

  child.stderr?.on("data", (chunk: Buffer) => {
    const text = chunk.toString().trim();
    if (text) options.onError(new Error(text));
  });

  child.on("error", (error: Error) => options.onError(error));
  child.on("exit", (code: number | null) => {
    rl.close();
    options.onExit?.(code);
  });

  return {
    sendChat(text: string) {
      writeLine(child, { type: "chat", text });
    },
    sendCommand(name: string, args: Record<string, unknown> = {}) {
      writeLine(child, { type: "command", name, args });
    },
    sendPermission(requestId: string, approved: boolean, scope: "once" | "session" = "once") {
      writeLine(child, {
        type: "permission_response",
        request_id: requestId,
        approved,
        scope,
      });
    },
    stop() {
      killProcessTree(child);
    },
  };
}
