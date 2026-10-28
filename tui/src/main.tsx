#!/usr/bin/env node
/** Exhibit's terminal entrypoint. */

import React from "react";
import { spawnSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { render } from "ink";
import { App } from "./components/App.js";
import { parseCliArgs, USAGE } from "./cli.js";

/**
 * Rebuild when launched through the globally linked `exhibit` command.
 *
 * `Exhibit.ps1` already does this, but npm's bin shim runs dist/main.js
 * directly. Without this guard, source edits stay invisible until a manual
 * `npm run build`.
 */
export function ensureFreshBuild(): void {
  const tuiRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
  const distMain = path.join(tuiRoot, "dist", "main.js");
  if (!existsSync(distMain)) return;
  const builtAt = statSync(distMain).mtimeMs;
  const inputs = [
    path.join(tuiRoot, "tsconfig.json"),
    path.join(tuiRoot, "package.json"),
  ];
  const srcRoot = path.join(tuiRoot, "src");
  const walk = (directory: string): void => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const full = path.join(directory, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (/\.tsx?$/.test(entry.name)) inputs.push(full);
    }
  };
  walk(srcRoot);
  if (!inputs.some((file) => statSync(file).mtimeMs > builtAt)) return;

  process.stderr.write("Exhibit: 检测到源码更新，正在编译 TUI…\n");
  const result = spawnSync(
    process.execPath,
    [path.join(tuiRoot, "node_modules", "typescript", "bin", "tsc"), "-p", "tsconfig.json"],
    { cwd: tuiRoot, stdio: "inherit" },
  );
  if (result.status !== 0) {
    throw new Error(`TUI 编译失败（tsc exit ${result.status ?? "unknown"}）`);
  }
}

const model = process.env.EXHIBIT_MODEL ?? "gpt-5.4-mini";

/** Read the TUI version from package.json without importing outside rootDir. */
function readVersion(): string {
  try {
    const tuiRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
    const pkgPath = path.join(tuiRoot, "package.json");
    const pkg = JSON.parse(readFileSync(pkgPath, "utf-8")) as { version?: string };
    return pkg.version ?? "0.1.0";
  } catch {
    return "0.1.0";
  }
}

let options;
try {
  ensureFreshBuild();
  options = parseCliArgs(process.argv.slice(2));
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  console.error(USAGE);
  process.exitCode = 2;
  options = null;
}

const version = readVersion();

if (options?.help) {
  console.log(USAGE);
} else if (options) {
  try {
    if (!statSync(options.repoPath).isDirectory()) {
      throw new Error(`目标路径不是目录: ${options.repoPath}`);
    }
    render(<App model={model} repoPath={options.repoPath} version={version} />, {
      exitOnCtrlC: false,
    });
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  }
}
