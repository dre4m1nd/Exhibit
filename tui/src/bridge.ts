/** Spawns the Python agent subprocess and forwards its protocol events. */

import { spawn, type ChildProcess } from "node:child_process";
import path from "node:path";
import readline from "node:readline";
import { fileURLToPath } from "node:url";
import { parseLine } from "./protocol.js";
import type { AgentMessage } from "./protocol.js";

export interface BridgeOptions {
  task: string;
  params: {
    repoPath: string;
    branch?: string;
    commitRange?: string;
    model?: string;
  };
  onMessage: (message: AgentMessage) => void;
  onError: (error: Error) => void;
  onExit?: (code: number | null) => void;
}

/** Locate the repository root (two levels up from dist/ or src/). */
export function findRepoRoot(): string {
  const here = path.dirname(fileURLToPath(import.meta.url));
  return path.resolve(here, "..", "..");
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

/** Start the agent and return the subprocess handle. */
export function startAgent(options: BridgeOptions): ChildProcess {
  const repoRoot = findRepoRoot();
  const python = resolvePython(repoRoot);
  const agentEntry = path.join(repoRoot, "agent", "app.py");

  const child = spawn(
    python,
    ["-u", "-m", "agent.app"],
    {
      cwd: repoRoot,
      stdio: ["pipe", "pipe", "pipe"],
      env: {
        ...process.env,
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

  const init = {
    type: "init",
    task: options.task,
    params: {
      repo_path: options.params.repoPath,
      branch: options.params.branch ?? null,
      commit_range: options.params.commitRange ?? null,
      model: options.params.model ?? null,
    },
  };
  child.stdin?.write(`${JSON.stringify(init)}\n`);

  return child;
}
