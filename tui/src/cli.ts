/** Command-line parsing for launching Exhibit in an arbitrary repository. */

import path from "node:path";

export interface CliOptions {
  repoPath: string;
  help: boolean;
}

const REPO_FLAGS = new Set(["-repo", "--repo", "--repo-path", "-r"]);

/** Parse `exhibit [path] [-Repo <path>]` and resolve the target from `cwd`. */
export function parseCliArgs(
  argv: string[],
  cwd: string = process.cwd(),
): CliOptions {
  let repo: string | undefined;
  let help = false;

  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index] ?? "";
    if (argument === "-h" || argument === "--help") {
      help = true;
      continue;
    }
    if (REPO_FLAGS.has(argument.toLowerCase())) {
      if (repo !== undefined) throw new Error("repository path was specified twice");
      const value = argv[index + 1];
      if (!value || REPO_FLAGS.has(value.toLowerCase())) {
        throw new Error(`${argument} requires a directory path`);
      }
      repo = value;
      index += 1;
      continue;
    }
    if (argument.startsWith("-")) {
      throw new Error(`unknown option: ${argument}`);
    }
    if (repo !== undefined) throw new Error("repository path was specified twice");
    repo = argument;
  }

  return {
    repoPath: path.resolve(cwd, repo ?? "."),
    help,
  };
}

export const USAGE = [
  "用法: exhibit [目录] [-Repo <目录>]",
  "",
  "不传目录时审查当前目录；-Repo 可指定当前项目中的子目录。",
].join("\n");
