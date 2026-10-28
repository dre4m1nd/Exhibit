import React, { useCallback, useEffect, useRef, useState } from "react";
import { Box, Text, useApp, useInput } from "ink";
import { startAgent, type AgentBridge } from "../bridge.js";
import type { ChatMessage } from "./ChatView.js";
import { ChatViewport } from "./ChatViewport.js";
import { PlanBanner } from "./PlanBanner.js";
import { LoginDialog, type LoginRequest } from "./LoginDialog.js";
import { ModelDialog } from "./ModelDialog.js";
import { PermissionPrompt, type PermissionScope } from "./PermissionPrompt.js";
import {
  moveSelection,
  parseCommandArgs,
  suggestionsFor,
} from "../commands.js";
import { parseModelCatalog, type ModelCatalog } from "../models.js";
import {
  appendTraceStep,
  summarizeTrace,
  type TraceStep,
} from "../trace.js";
import { theme } from "../theme.js";
import type { AgentMessage } from "../protocol.js";

type Screen =
  | "chat"
  | "login"
  | "login-busy"
  | "model"
  | "model-busy"
  | "permission"
  | "confirm";
/** Commands that ask the user to confirm before reaching the agent. */
const CONFIRM_COMMANDS = new Set(["/logout", "/clear"]);
const CONFIRM_HINT: Record<string, string> = {
  "/logout": "删除当前供应商凭据？输入 y 确认，其它键取消",
  "/clear": "清空当前对话上下文？输入 y 确认，其它键取消",
};

interface PermissionRequest {
  requestId: string;
  path: string;
  action: string;
  summary: string;
  sessionId: string;
  trusted: boolean;
}

/** Shown once per run when input arrives while the agent is still streaming. */
const BUSY_HINT = "运行中：输入已保留，完成或按 Ctrl+C 中断后再按 Enter 发送";

const PERMISSION_STATUS: Record<PermissionScope, string> = {
  once: "已允许本次修改",
  session: "已允许本会话后续写入",
  reject: "已拒绝修改",
};

export function App({
  model,
  repoPath,
}: {
  model: string;
  repoPath: string;
}) {
  const { exit } = useApp();
  const [screen, setScreen] = useState<Screen>("chat");
  const [activeModel, setActiveModel] = useState(model);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState("就绪 · 输入 / 查看命令");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [planMode, setPlanMode] = useState(false);
  const [loginError, setLoginError] = useState("");
  const [modelCatalog, setModelCatalog] = useState<ModelCatalog | null>(null);
  const [modelError, setModelError] = useState("");
  const [permission, setPermission] = useState<PermissionRequest | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [selected, setSelected] = useState(-1);
  const [elapsed, setElapsed] = useState(0);
  const [draft, setDraft] = useState<ChatMessage | null>(null);
  const busyStart = useRef<number | null>(null);
  const busyHint = useRef(false);
  const bridge = useRef<AgentBridge | null>(null);
  const screenRef = useRef<Screen>("chat");
  const nextId = useRef(0);
  const stream = useRef("");
  const assistantId = useRef<number | null>(null);
  const [traceExpanded, setTraceExpanded] = useState(false);
  const [liveTrace, setLiveTrace] = useState<TraceStep[]>([]);
  const traceRef = useRef<{ thinking: string; steps: TraceStep[] }>({
    thinking: "",
    steps: [],
  });
  const append = useCallback((role: ChatMessage["role"], text: string) => {
    const id = nextId.current++;
    setMessages((previous) => [...previous, { id, role, text }]);
    return id;
  }, []);

  const commit = useCallback(
    (
      role: ChatMessage["role"],
      text: string,
      options: Pick<ChatMessage, "kind" | "ok" | "duration" | "steps" | "collapsedSummary"> = {},
    ) => {
      const id = nextId.current++;
    setMessages((previous) => [...previous, { id, role, text, ...options }]);
      return id;
    },
    [],
  );

  const finishBusy = useCallback(
    (nextStatus = "就绪") => {
      const duration =
        busyStart.current === null
          ? 0
          : (Date.now() - busyStart.current) / 1000;
      setElapsed(duration);
      setDraft((current) =>
        current?.role === "assistant" && current.kind === undefined && duration > 0
          ? { ...current, duration }
          : current,
      );
      setBusy(false);
      setStatus(nextStatus);
      busyStart.current = null;
      busyHint.current = false;
      return duration;
    },
    [],
  );

  const takeTrace = useCallback((): Pick<
    ChatMessage,
    "steps" | "collapsedSummary"
  > => {
    const steps = traceRef.current.steps;
    if (steps.length === 0) {
      traceRef.current = { thinking: "", steps: [] };
      setLiveTrace([]);
      return {};
    }
    const summary = summarizeTrace(steps);
    traceRef.current = { thinking: "", steps: [] };
    setLiveTrace([]);
    return { steps, collapsedSummary: summary };
  }, []);

  const commitTrace = useCallback(() => {
    const trace = takeTrace();
    if (!trace.steps || trace.steps.length === 0) return;
    commit("system", trace.collapsedSummary ?? "", {
      kind: "trace",
      ...trace,
    });
  }, [commit, takeTrace]);

  const addTraceStep = useCallback((step: TraceStep) => {
    traceRef.current.steps = appendTraceStep(traceRef.current.steps, step);
    setLiveTrace(traceRef.current.steps);
  }, []);

  // Track how long the agent has been working, updating once per second.
  const updateElapsed = useCallback(() => {
    if (busyStart.current !== null) {
      setElapsed((Date.now() - busyStart.current) / 1000);
    }
  }, []);

  useEffect(() => {
    if (busy) {
      if (busyStart.current === null) busyStart.current = Date.now();
      const timer = setInterval(updateElapsed, 1000);
      return () => clearInterval(timer);
    }
    return undefined;
  }, [busy, updateElapsed]);

  useEffect(() => {
    screenRef.current = screen;
  }, [screen]);

  useEffect(() => {
    if (confirming) setScreen("confirm");
    else if (screen === "confirm") setScreen("chat");
  }, [confirming, screen]);

  const handleCommandResult = useCallback(
    (name: string, data: Record<string, unknown>) => {
      if (name === "/login") {
        setScreen("chat");
        setLoginError("");
        setActiveModel(String(data.model ?? ""));
        append("system", `已登录 ${String(data.provider ?? "")} · ${String(data.model ?? "")}`);
        setStatus("登录成功");
        return;
      }
      if (name === "/plan") {
        const active = data.mode === "plan";
        setPlanMode(active);
        setStatus(active ? "PLAN · 只读分析模式" : "已退出计划模式");
        append(
          "system",
          active
            ? "已进入计划模式：只读分析，写工具不可用"
            : "已退出计划模式：可以继续修改文件",
        );
        return;
      }
      if (name === "/fork") {
        append("system", `已创建会话 ${String(data.display_name ?? data.session ?? "")}`);
        return;
      }
      if (name === "/status") {
        append("system", formatStatus(data));
        return;
      }
      if (name === "/model" && data.kind === "model_catalog") {
        const catalog = parseModelCatalog(data);
        if (catalog) {
          setModelCatalog(catalog);
          setModelError("");
          const available = catalog.providers.length > 0;
          setScreen(available ? "model" : "chat");
          if (!available) {
            append("system", "尚未登录任何供应商，请先输入 /login。");
            setStatus("没有可用模型");
          }
          return;
        }
      }
      if (name === "/model" && data.kind === "model_selected") {
        const selectedModel = String(data.model ?? "");
        setActiveModel(selectedModel);
        setModelCatalog(null);
        setModelError("");
        setScreen("chat");
        append(
          "system",
          `已切换为 ${String(data.provider ?? "")} · ${selectedModel}`,
        );
        setStatus("模型已切换");
        return;
      }
      if (name === "/quit" && data.can_quit === true) {
        exit();
        return;
      }
      if (name === "/provider" && Array.isArray(data.providers)) {
        append(
          "system",
          (data.providers as Array<Record<string, unknown>>)
            .map((item) => `${String(item.label)} · ${item.logged_in ? "已登录" : "未登录"}`)
            .join("\n"),
        );
        return;
      }
      if (name === "/provider" && data.provider) {
        setActiveModel(String(data.model ?? ""));
        append(
          "system",
          `已切换为 ${String(data.provider)} · ${String(data.model ?? "")}`,
        );
        return;
      }
      if (name === "/init" || name === "/review" || name === "/diff") {
        if (data.empty !== true) {
          append("system", `已完成 ${name}`);
        }
        return;
      }
      // Every remaining command must surface its structured result in chat
      // via the shared formatter below.
      const text = describeCommandResult(name, data);
      if (text) append("system", text);
  },
  [append, exit],
);

  const handleMessage = useCallback(
    (message: AgentMessage) => {
      switch (message.type) {
        case "chat_delta":
          stream.current += message.text;
          if (assistantId.current === null) {
            assistantId.current = nextId.current++;
          }
          setDraft({
            id: assistantId.current,
            role: "assistant",
            text: stream.current,
          });
          break;
        case "chat_done":
          {
            const text = message.text || stream.current;
            setFailed(false);
            const duration = finishBusy();
            commitTrace();
            if (text) commit("assistant", text, { duration });
          }
          setDraft(null);
          stream.current = "";
          assistantId.current = null;
          break;
        case "command_result":
          commitTrace();
          handleCommandResult(message.name, message.data);
          finishBusy(
            message.name === "/diff" && message.data.empty === true
              ? "没有可审查的变更"
              : "就绪",
          );
          break;
        case "permission_request":
          setPermission({
            requestId: message.request_id,
            path: message.path,
            action: message.action,
            summary: message.summary,
            sessionId: message.session_id,
            trusted: message.trusted,
          });
          setScreen("permission");
          break;
        case "report":
          {
            setFailed(false);
            const duration = finishBusy();
            commitTrace();
            commit("assistant", message.markdown, { duration });
          }
          setDraft(null);
          assistantId.current = null;
          break;
        case "error":
          {
            setFailed(true);
            const duration = finishBusy("出错");
            commitTrace();
            commit("system", message.message, { duration });
          }
          setDraft(null);
          assistantId.current = null;
          if (screenRef.current === "model-busy") {
            setModelError(message.message);
            setScreen("model");
            return;
          }
          if (screenRef.current === "login-busy") {
            setLoginError(message.message);
            setScreen("login");
            return;
          }
          break;
        case "status":
          setStatus(message.detail || message.phase);
          break;
        case "session":
          setStatus(sessionStatus(message.data));
          break;
        case "tool_call":
          setStatus(`${message.name}(${formatArgs(message.args)})`);
          addTraceStep({
            type: "tool",
            text: `${message.name}(${formatArgs(message.args)})`,
          });
          break;
        case "tool_result":
          setStatus(`${message.name} → ${message.summary}`);
          addTraceStep({
            type: "tool-result",
            text: `${message.name} → ${message.summary}`,
            ok: message.ok,
          });
          break;
        case "thinking_delta":
          addTraceStep({
            type: "thinking",
            text: message.text,
          });
          break;
        default:
          break;
      }
    },
    [addTraceStep, append, commit, commitTrace, finishBusy, handleCommandResult],
  );

  useEffect(() => {
    bridge.current = startAgent({
      repoPath,
      onMessage: handleMessage,
      onError: (error) => {
        append("system", error.message);
        setBusy(false);
      },
      onExit: (code) => {
        if (code !== null && code !== 0) {
          append("system", `智能体进程退出，代码 ${code}`);
        }
      },
    });
    return () => bridge.current?.stop();
  }, [append, handleMessage, repoPath]);

  const submit = useCallback(
    (value: string) => {
      const text = value.trim();
      if (!text) return;
      if (busy) {
        // Never drop input silently: keep the draft and explain once per run.
        if (!busyHint.current) {
          busyHint.current = true;
          append("system", BUSY_HINT);
        }
        return;
      }
      setFailed(false);
      setDraft(null);
      stream.current = "";
      assistantId.current = null;
      setInput("");
      setSelected(-1);
      if (text === "/quit") {
        append("user", text);
        setBusy(true);
        bridge.current?.sendCommand("/quit");
        return;
      }
      if (text === "/login") {
        append("user", text);
        setLoginError("");
        setScreen("login");
        return;
      }
      if (text === "/model") {
        append("user", text);
        setBusy(true);
        setStatus("发现模型目录");
        bridge.current?.sendCommand("/model");
        return;
      }
      if (text.startsWith("/") && CONFIRM_COMMANDS.has((text.split(/\s+/)[0] ?? "").toLowerCase())) {
        append("user", text);
        setConfirming((text.split(/\s+/)[0] ?? "").toLowerCase());
        return;
      }
      if (text.startsWith("/")) {
        // Echo every slash command so the conversation history shows what
        // was requested, including commands that open a dedicated screen.
        append("user", text);
        const [name, ...rest] = text.split(/\s+/);
        if (name === "/model" && rest[0]) {
          // Preserve direct switching for automation and power users.
          setBusy(true);
          setStatus("切换模型");
          bridge.current?.sendCommand("/model", { model: rest[0] });
          return;
        }
        setBusy(true);
        bridge.current?.sendCommand(name ?? "", parseCommandArgs(name ?? "", rest));
        return;
      }
      append("user", text);
      setBusy(true);
      setStatus("模型推理中");
      bridge.current?.sendChat(text);
    },
    [append, busy],
  );

  useInput(
    (value, key) => {
      const candidates = suggestionsFor(input, planMode);
      if (candidates.length > 0) {
        if (key.upArrow) {
          setSelected((current) => moveSelection(current, -1, candidates.length));
          return;
        }
        if (key.downArrow) {
          setSelected((current) => moveSelection(current, 1, candidates.length));
          return;
        }
        const active = candidates[selected] ?? candidates[0];
        if (key.tab && active) {
          const next = active.insert + (active.takesArguments ? " " : "");
          setInput(next);
          setSelected(suggestionsFor(next, planMode).length > 0 ? 0 : -1);
          return;
        }
        if (key.return && active) {
          if (active.execute) {
            setInput("");
            setSelected(-1);
            submit(active.execute);
            return;
          }
          // Commands that take arguments are only filled in, so Enter cannot
          // accidentally kick off a full-repo review.
          const next = active.insert + (active.takesArguments ? " " : "");
          setInput(next);
          setSelected(suggestionsFor(next, planMode).length > 0 ? 0 : -1);
          return;
        }
      }
      if (key.return) {
        submit(input);
        return;
      }
      if (key.backspace || key.delete) {
        const next = input.slice(0, -1);
        setInput(next);
        setSelected(suggestionsFor(next, planMode).length > 0 ? 0 : -1);
        return;
      }
      if (key.ctrl && value === "c") {
        // Hard exit: kill the agent subprocess and leave immediately so a
        // stuck /quit (e.g. blocked by unconfirmed writes) can't leave an
        // orphaned TUI + agent pair behind. Graceful exit stays on /quit.
        bridge.current?.stop();
        exit();
        return;
      }
      if (key.ctrl && value === "t") {
        setTraceExpanded((current) => !current);
        return;
      }
      if (value && !key.ctrl && !key.meta) {
        const next = input + value;
        setInput(next);
        setSelected(suggestionsFor(next, planMode).length > 0 ? 0 : -1);
      }
    },
    { isActive: screen === "chat" },
  );

  const finishLogin = (request: LoginRequest) => {
    setLoginError("");
    setScreen("login-busy");
    setStatus("校验并保存凭据");
    bridge.current?.sendCommand("/login", {
      provider: request.provider,
      api_key: request.apiKey,
      model: request.model,
      base_url: request.baseUrl,
    });
  };

  const selectModel = (provider: string, modelId: string) => {
    setModelError("");
    setScreen("model-busy");
    setBusy(true);
    bridge.current?.sendCommand("/model", { provider, model: modelId });
  };

  const retryModelCatalog = () => {
    setModelError("");
    setModelCatalog(null);
    setScreen("chat");
    setBusy(true);
    setStatus("发现模型目录");
    bridge.current?.sendCommand("/model");
  };

  const decidePermission = (scope: PermissionScope) => {
    if (permission) {
      bridge.current?.sendPermission(
        permission.requestId,
        scope !== "reject",
        scope === "session" ? "session" : "once",
      );
    }
    setPermission(null);
    setScreen("chat");
    setStatus(PERMISSION_STATUS[scope]);
  };

  const runConfirmedCommand = useCallback(
    (name: string) => {
      setConfirming(null);
      setBusy(true);
      bridge.current?.sendCommand(name, { confirm: true });
    },
    [],
  );

  useInput(
    (value, key) => {
      if (confirming === null) return;
      if (key.escape || (key.ctrl && value === "c")) {
        setConfirming(null);
        return;
      }
      if (value.toLowerCase() === "y") runConfirmedCommand(confirming);
      else setConfirming(null);
    },
    { isActive: screen === "confirm" },
  );

  return (
    <Box flexDirection="column">
      <PlanBanner active={planMode} />
      {screen === "login" || screen === "login-busy" ? (
        <LoginDialog
          onCancel={() => setScreen("chat")}
          onSubmit={finishLogin}
          busy={screen === "login-busy"}
          error={loginError}
        />
      ) : (screen === "model" || screen === "model-busy") && modelCatalog ? (
        <ModelDialog
          catalog={modelCatalog}
          busy={screen === "model-busy"}
          error={modelError}
          onCancel={() => {
            setModelCatalog(null);
            setModelError("");
            setScreen("chat");
          }}
          onRetry={retryModelCatalog}
          onSelect={selectModel}
        />
      ) : screen === "permission" && permission ? (
        <PermissionPrompt
          path={permission.path}
          action={permission.action}
          summary={permission.summary}
          trusted={permission.trusted}
          onDecision={decidePermission}
        />
      ) : screen === "confirm" && confirming ? (
        <Box flexDirection="column" borderStyle="round" borderColor={theme.warn} paddingX={1}>
          <Text color={theme.warn} bold>
            需要确认 {confirming}
          </Text>
          <Text color={theme.text}>{CONFIRM_HINT[confirming] ?? "确认执行？"}</Text>
        </Box>
      ) : (
        <ChatViewport
          messages={messages}
          draft={draft}
          input={input}
          status={status}
          planMode={planMode}
          busy={busy}
          selected={selected}
          elapsed={elapsed}
          traceExpanded={traceExpanded}
          liveTrace={liveTrace}
          failed={failed}
        />
      )}
      {screen !== "chat" ? <Text color={theme.muted}>Esc 返回 · Ctrl+C 取消</Text> : null}
    </Box>
  );
}

/**
 * Human-readable result for slash commands that don't open a dedicated screen
 * or stream a report. Returns "" for commands without a meaningful result line
 * so callers can skip echoing. Keeping this pure makes every command's result
 * echoable and unit-testable, and covers commands the chat previously dropped.
 */
export function describeCommandResult(
  name: string,
  data: Record<string, unknown>,
): string {
  switch (name) {
    case "/logout":
      return `已退出登录 ${String(data.provider ?? "")}`;
    case "/clear":
      return "对话上下文已清空";
    case "/compact":
      return `已压缩上下文，保留 ${String(data.messages ?? 0)} 条，文件变更：${
        Array.isArray(data.changed_files)
          ? (data.changed_files as unknown[]).join(", ") || "无"
          : "无"
      }`;
    case "/permissions":
      return `模式 ${String(data.mode ?? "")} · 写入权限 ${
        data.writes ? "开启" : "仅只读"
      } · 确认策略 ${String(data.confirmation ?? "")}`;
    case "/files":
      return `已读 ${formatList(data.read_files)} · 已改 ${formatList(data.changed_files)}`;
    case "/undo":
      return data.undone ? `已撤销：${String(data.undone)}` : "没有可撤销的修改";
    case "/commands":
      return formatCommands(data.commands);
    default:
      return `${name}: ${JSON.stringify(data)}`;
  }
}

/** Commands arrive as `{name, description}` objects, not plain strings. */
function formatCommands(value: unknown): string {
  const rows = Array.isArray(value) ? (value as unknown[]) : [];
  const lines = rows
    .map((item) => {
      if (item && typeof item === "object") {
        const record = item as Record<string, unknown>;
        const name = String(record.name ?? "").trim();
        const description = String(record.description ?? "").trim();
        if (name) return description ? `${name} · ${description}` : name;
      }
      return String(item ?? "").trim();
    })
    .filter((line) => line.length > 0);
  if (lines.length === 0) return "没有可用命令";
  return ["可用命令：", ...lines].join("\n");
}

function formatList(value: unknown, prefix = ""): string {
  const items = Array.isArray(value)
    ? (value as unknown[]).map((item) =>
        item && typeof item === "object" ? JSON.stringify(item) : String(item),
      )
    : [];
  if (items.length === 0) return prefix ? `${prefix}无` : "无";
  return prefix ? `${prefix}${items.join(", ")}` : items.join(", ");
}

/**
 * Status-bar text for a session event.
 *
 * Carries the mode plus the provider and model the agent will really call, so
 * the bar never has to guess from environment defaults.
 */
export function sessionStatus(data: Record<string, unknown>): string {
  const parts = [String(data.session ?? "main")];
  if (String(data.mode ?? "") === "plan") parts.push("plan");
  const provider = String(data.provider ?? "");
  const model = String(data.model ?? "");
  if (provider || model) {
    parts.push([provider, model].filter(Boolean).join(" · "));
  }
  return `会话 ${parts.join(" · ")}`;
}

function formatStatus(data: Record<string, unknown>): string {
  return Object.entries(data)
    .map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(", ") : String(value)}`)
    .join("\n");
}

function formatArgs(args: Record<string, unknown>): string {
  return Object.entries(args)
    .map(([key, value]) => `${key}=${typeof value === "string" ? value : JSON.stringify(value)}`)
    .join(", ");
}
