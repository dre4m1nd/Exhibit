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
  SLASH_COMMANDS,
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
import {
  describeCommandResult,
  formatArgs,
  formatStatus,
  sessionStatus,
} from "../formatters.js";

type Screen =
  | "chat"
  | "login"
  | "login-busy"
  | "model"
  | "model-busy"
  | "permission"
  | "confirm";
/** Commands that ask the user to confirm before reaching the agent. */
const CONFIRM_COMMANDS = new Set(
  SLASH_COMMANDS.filter((command) => command.requiresConfirm).map(
    (command) => command.name,
  ),
);
const CONFIRM_HINTS = new Map(
  SLASH_COMMANDS.filter((command) => command.confirmHint).map((command) => [
    command.name,
    command.confirmHint ?? "",
  ]),
);

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

export function App({ repoPath }: { repoPath: string }) {
  const { exit } = useApp();
  const [screen, setScreen] = useState<Screen>("chat");
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
  const traceRef = useRef<{ steps: TraceStep[] }>({ steps: [] });
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

  // Computed once per input change instead of once per keystroke per view.
  const suggestions = React.useMemo(
    () => suggestionsFor(input, planMode),
    [input, planMode],
  );

  /** Clear the streaming draft; every terminal event ends one stream. */
  const resetStream = useCallback(() => {
    setDraft(null);
    stream.current = "";
    assistantId.current = null;
  }, []);

  const takeTrace = useCallback((): Pick<
    ChatMessage,
    "steps" | "collapsedSummary"
  > => {
    const steps = traceRef.current.steps;
    traceRef.current = { steps: [] };
    setLiveTrace([]);
    if (steps.length === 0) return {};
    return { steps, collapsedSummary: summarizeTrace(steps) };
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
          resetStream();
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
          resetStream();
          break;
        case "error":
          {
            setFailed(true);
            const duration = finishBusy("出错");
            commitTrace();
            commit("system", message.message, { duration });
          }
          resetStream();
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
          {
            const call = `${message.name}(${formatArgs(message.args)})`;
            setStatus(call);
            addTraceStep({ type: "tool", text: call });
          }
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
    [
      addTraceStep,
      append,
      commit,
      commitTrace,
      finishBusy,
      handleCommandResult,
      resetStream,
    ],
  );

  useEffect(() => {
    bridge.current = startAgent({
      repoPath,
      onMessage: handleMessage,
      onError: (error) => {
        append("system", error.message);
        resetStream();
        finishBusy("出错");
      },
      onExit: (code) => {
        append(
          "system",
          code === null
            ? "智能体进程已断开，无法继续发送消息"
            : `智能体进程退出，代码 ${code}，无法继续发送消息`,
        );
      },
    });
    return () => bridge.current?.stop();
  }, [append, finishBusy, handleMessage, repoPath, resetStream]);

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
      resetStream();
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
      const [name = "", ...rest] = text.split(/\s+/);
      const command = name.toLowerCase();
      if (text.startsWith("/") && CONFIRM_COMMANDS.has(command)) {
        append("user", text);
        setConfirming(command);
        return;
      }
      if (text.startsWith("/")) {
        // Echo every slash command so the conversation history shows what
        // was requested, including commands that open a dedicated screen.
        append("user", text);
        const args = parseCommandArgs(name, rest);
        setBusy(true);
        if (command === "/model" && args.model) setStatus("切换模型");
        bridge.current?.sendCommand(name, args);
        return;
      }
      append("user", text);
      setBusy(true);
      setStatus("模型推理中…");
      bridge.current?.sendChat(text);
    },
    [append, busy, resetStream],
  );

  useInput(
    (value, key) => {
      const candidates = suggestions;
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
    setStatus("正在发现模型…");
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
          <Text color={theme.text}>
            {CONFIRM_HINTS.get(confirming) ?? "确认执行？"}
          </Text>
        </Box>
      ) : (
        <ChatViewport
          messages={messages}
          draft={draft}
          input={input}
          status={status}
          planMode={planMode}
          busy={busy}
          suggestions={suggestions}
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

