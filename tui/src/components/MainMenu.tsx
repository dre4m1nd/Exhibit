import React, { useState } from "react";
import { Box, Text, useInput } from "ink";
import { theme } from "../theme.js";
import { TASKS, TASK_TITLES, type TaskName } from "../protocol.js";

export interface TaskRequest {
  task: TaskName;
  repoPath: string;
  branch: string;
  commitRange: string;
}

const HINTS: Record<TaskName, string> = {
  arch_overview: "看懂项目：模块划分、职责、依赖与阅读路径",
  arch_audit: "找架构失职：越层、循环依赖、职责失衡",
  review_repo: "全量体检：正确性、健壮性、安全、可维护性",
  review_git: "PR 式审查：未提交改动 / commit range / 分支 diff",
};

/** The task picker plus the parameters needed for the chosen task. */
export function MainMenu({
  defaultRepoPath,
  onStart,
}: {
  defaultRepoPath: string;
  onStart: (request: TaskRequest) => void;
}) {
  const [cursor, setCursor] = useState(0);
  const [stage, setStage] = useState<"menu" | "params">("menu");
  const [repoPath, setRepoPath] = useState(defaultRepoPath);
  const [branch, setBranch] = useState("");
  const [commitRange, setCommitRange] = useState("");
  const [field, setField] = useState(0);
  const task = TASKS[cursor] as TaskName;
  const isGitTask = task === "review_git";

  useInput((input, key) => {
    if (stage === "menu") {
      if (key.upArrow) setCursor((c) => Math.max(0, c - 1));
      else if (key.downArrow) setCursor((c) => Math.min(TASKS.length - 1, c + 1));
      else if (key.return) setStage("params");
      else if (input === "q") process.exit(0);
      return;
    }

    // stage === "params"
    if (key.escape) {
      if (field === 0) setStage("menu");
      else setField((f) => f - 1);
      return;
    }
    if (key.return) {
      if (!isGitTask || field === 2) {
        onStart({ task, repoPath, branch, commitRange });
        return;
      }
      setField(field + 1);
      return;
    }
    if (key.backspace || key.delete) {
      const drop = (value: string) => value.slice(0, -1);
      if (field === 0) setRepoPath(drop);
      else if (field === 1) setBranch(drop);
      else setCommitRange(drop);
      return;
    }
    if (!input) return;
    const append = (value: string) => value + input;
    if (field === 0) setRepoPath(append);
    else if (field === 1) setBranch(append);
    else setCommitRange(append);
  });

  if (stage === "params") {
    return (
      <Box flexDirection="column" borderStyle="round" borderColor={theme.accent} paddingX={2}>
        <Text color={theme.accent} bold>
          {TASK_TITLES[task]}
        </Text>
        <Text color={theme.muted}>{HINTS[task]}</Text>
        <Box height={1} />
        <Field label="仓库路径" value={repoPath} focused={field === 0} />
        {isGitTask ? (
          <>
            <Field label="分支/基线 (可选)" value={branch} focused={field === 1} />
            <Field label="commit range (可选)" value={commitRange} focused={field === 2} />
          </>
        ) : null}
        <Box height={1} />
        <Text color={theme.muted}>
          {field > 0 ? "Esc 返回上一项 · " : "Esc 返回菜单 · "}Enter 开始
        </Text>
      </Box>
    );
  }

  return (
    <Box flexDirection="column" borderStyle="round" borderColor={theme.accent} paddingX={2}>
      <Text color={theme.accent} bold>
        EXHIBIT
      </Text>
      <Text color={theme.muted}>选择一项任务开始（↑↓ 选择 · Enter 确认 · q 退出）</Text>
      <Box height={1} />
      {TASKS.map((name, index) => (
        <Box key={name}>
          <Text color={index === cursor ? theme.accent : theme.muted}>
            {index === cursor ? "❯" : " "} {index + 1}. {TASK_TITLES[name]}
          </Text>
        </Box>
      ))}
      <Box height={1} />
      <Text color={theme.muted}>{HINTS[task]}</Text>
    </Box>
  );
}

function Field({ label, value, focused }: { label: string; value: string; focused: boolean }) {
  return (
    <Text color={focused ? theme.text : theme.muted}>
      {label}: <Text color={theme.accent}>{value || "（空）"}</Text>
      {focused ? <Text color={theme.accent}>▌</Text> : null}
    </Text>
  );
}
