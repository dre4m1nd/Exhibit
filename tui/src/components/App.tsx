import React, { useCallback, useEffect, useRef, useState } from "react";
import { Box, Text, useApp, useInput } from "ink";
import type { ChildProcess } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { startAgent, findRepoRoot } from "../bridge.js";
import { Header } from "./Header.js";
import { AgentLog, type LogEntry } from "./AgentLog.js";
import { MainMenu, type TaskRequest } from "./MainMenu.js";
import { ReportView } from "./ReportView.js";
import { theme } from "../theme.js";
import { TASK_TITLES, type AgentMessage } from "../protocol.js";

type Phase = "menu" | "running" | "report";

/** The top-level state machine: menu -> running -> report. */
export function App({ model }: { model: string }) {
  const { exit } = useApp();
  const [phase, setPhase] = useState<Phase>("menu");
  const [request, setRequest] = useState<TaskRequest | null>(null);
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [report, setReport] = useState("");
  const [status, setStatus] = useState({ phase: "scanning", detail: "" });
  const [elapsed, setElapsed] = useState(0);
  const [fatal, setFatal] = useState("");
  const childRef = useRef<ChildProcess | null>(null);
  const nextId = useRef(0);
  const reportRef = useRef("");
  const fatalRef = useRef("");
  const runId = useRef(0);

  useEffect(() => {
    if (phase !== "running") return;
    const startedAt = Date.now();
    // Tick once per second: a 100ms tick repaints the whole Ink tree and
    // floods the terminal with escape sequences.
    const timer = setInterval(() => {
      const seconds = Math.floor((Date.now() - startedAt) / 1000);
      setElapsed((previous) => (previous === seconds ? previous : seconds));
    }, 1000);
    return () => clearInterval(timer);
  }, [phase]);

  useEffect(() => {
    return () => {
      childRef.current?.kill();
    };
  }, []);

  const push = useCallback((kind: LogEntry["kind"], text: string) => {
    setEntries((previous) => {
      const entry = { id: nextId.current++, kind, text };
      const next = [...previous, entry];
      return next.length > 200 ? next.slice(next.length - 200) : next;
    });
  }, []);

  const handleStart = useCallback(
    (next: TaskRequest) => {
      childRef.current?.kill();
      childRef.current = null;
      const currentRun = ++runId.current;
      setRequest(next);
      setEntries([]);
      setReport("");
      reportRef.current = "";
      setFatal("");
      fatalRef.current = "";
      setElapsed(0);
      setStatus({ phase: "scanning", detail: "启动智能体" });
      setPhase("running");

      childRef.current = startAgent({
        task: next.task,
        params: {
          repoPath: next.repoPath,
          branch: next.branch,
          commitRange: next.commitRange,
          model: model || undefined,
        },
        onMessage: (message: AgentMessage) => {
          // Ignore stragglers from an aborted previous run.
          if (currentRun !== runId.current) return;
          handleMessage(message);
        },
        onError: (error: Error) => {
          if (currentRun !== runId.current) return;
          push("error", error.message);
        },
        onExit: (code) => {
          childRef.current = null;
          if (currentRun !== runId.current) return;
          if (code !== 0 && !reportRef.current && !fatalRef.current) {
            push("error", `智能体进程退出，代码 ${code ?? "unknown"}`);
          }
        },
      });
    },
    [model, push],
  );

  const handleMessage = useCallback(
    (message: AgentMessage) => {
      switch (message.type) {
        case "status":
          setStatus({ phase: message.phase, detail: message.detail });
          // "tool" is already rendered as its own ▸ line; don't duplicate it.
          if (message.phase !== "thinking" && message.phase !== "tool") {
            push("status", `${message.phase} ${message.detail}`.trim());
          }
          break;
        case "tool_call":
          push("tool", `${message.name}(${formatArgs(message.args)})`);
          break;
        case "tool_result":
          push("result", `${message.name} → ${message.summary}`);
          break;
        case "token":
          // Draft text is intentionally not rendered: the final report is the
          // only thing worth showing, and repainting per token is wasteful.
          break;
        case "reset":
          break;
        case "report":
          reportRef.current = message.markdown;
          setReport(message.markdown);
          setPhase("report");
          break;
        case "error":
          fatalRef.current = message.message;
          setFatal(message.message);
          push("error", message.message);
          setPhase("report");
          break;
        case "done":
          setPhase((current) => {
            if (current !== "running") return current;
            return "report";
          });
          break;
      }
    },
    [push],
  );

  const handleSave = useCallback(() => {
    const target = path.join(findRepoRoot(), "EXHIBIT_REPORT.md");
    fs.writeFileSync(target, report, "utf8");
    push("status", `已保存到 ${target}`);
  }, [push, report]);

  useInput((input, key) => {
    if (phase === "running" && (input === "q" || key.escape)) {
      runId.current += 1;
      childRef.current?.kill();
      childRef.current = null;
      setPhase("menu");
    }
  });

  if (phase === "menu" || !request) {
    return (
      <MainMenu
        defaultRepoPath={process.cwd()}
        onStart={handleStart}
      />
    );
  }

  return (
    <Box flexDirection="column">
      <Header
        taskTitle={TASK_TITLES[request.task]}
        repoPath={request.repoPath}
        model={model || "默认"}
      />
      <Box height={1} />
      <StatusLine status={status} running={phase === "running"} elapsed={elapsed} />
      <Box height={1} />
      {phase === "report" ? (
        fatal ? (
          <Box flexDirection="column" borderStyle="round" borderColor={theme.danger} paddingX={1}>
            <Text color={theme.danger} bold>
              任务失败
            </Text>
            <Text color={theme.text}>{fatal}</Text>
            <Text color={theme.muted}>按 q 返回菜单</Text>
          </Box>
        ) : (
          <ReportView
            markdown={report}
            onSave={handleSave}
            onQuit={() => setPhase("menu")}
          />
        )
      ) : (
        <AgentLog entries={entries} />
      )}
    </Box>
  );
}

function StatusLine({
  status,
  running,
  elapsed,
}: {
  status: { phase: string; detail: string };
  running: boolean;
  elapsed: number;
}) {
  const seconds = String(elapsed);
  const glyph = running ? "◐" : "✓";
  return (
    <Box borderStyle="round" borderColor={running ? theme.accent : theme.border} paddingX={1}>
      <Text color={running ? theme.accent : theme.muted}>{glyph}</Text>
      <Text color={theme.muted}> {status.phase} </Text>
      <Text color={theme.text}>{status.detail}</Text>
      <Box flexGrow={1} />
      <Text color={theme.muted}>
        {seconds}s{running ? "  q 中断" : ""}
      </Text>
    </Box>
  );
}

function formatArgs(args: Record<string, unknown>): string {
  const parts = Object.entries(args).map(([key, value]) => {
    const rendered = typeof value === "string" ? value : JSON.stringify(value);
    return `${key}=${rendered}`;
  });
  return parts.join(", ");
}
