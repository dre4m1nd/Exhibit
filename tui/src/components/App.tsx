import React, { useCallback, useEffect, useRef, useState } from "react";
import { Box, Text, useApp, useInput } from "ink";
import { startAgent, type AgentBridge } from "../bridge.js";
import { Header } from "./Header.js";
import { ChatView, type ChatMessage } from "./ChatView.js";
import { PlanBanner } from "./PlanBanner.js";
import { LoginDialog, type LoginRequest } from "./LoginDialog.js";
import { PermissionPrompt, type PermissionScope } from "./PermissionPrompt.js";
import {
  moveSelection,
  parseCommandArgs,
  suggestionsFor,
} from "../commands.js";
import { theme } from "../theme.js";
import type { AgentMessage } from "../protocol.js";

type Screen = "chat" | "login" | "login-busy" | "permission" | "confirm";
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

const PERMISSION_STATUS: Record<PermissionScope, string> = {
  once: "已允许本次修改",
  session: "已允许本会话后续写入",
  reject: "已拒绝修改",
};

export function App({ model, repoPath }: { model: string; repoPath: string }) {
  const { exit } = useApp();
  const [screen, setScreen] = useState<Screen>("chat");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState("就绪 · 输入 / 查看命令");
  const [busy, setBusy] = useState(false);
  const [planMode, setPlanMode] = useState(false);
  const [loginError, setLoginError] = useState("");
  const [permission, setPermission] = useState<PermissionRequest | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [selected, setSelected] = useState(-1);
  const [elapsed, setElapsed] = useState(0);
  const busyStart = useRef<number | null>(null);
  const bridge = useRef<AgentBridge | null>(null);
  const screenRef = useRef<Screen>("chat");
  const nextId = useRef(0);
  const stream = useRef("");

  const append = useCallback((role: ChatMessage["role"], text: string) => {
    setMessages((previous) => [
      ...previous.slice(-199),
      { id: nextId.current++, role, text },
    ]);
  }, []);

  const finishBusy = useCallback(
    (nextStatus = "就绪") => {
      const duration =
        busyStart.current === null
          ? 0
          : (Date.now() - busyStart.current) / 1000;
      // Keep the completed duration on the final assistant message so the
      // history shows how long each review took, not just the latest run.
      if (duration > 0) {
        setMessages((previous) => {
          for (let index = previous.length - 1; index >= 0; index -= 1) {
            const item = previous[index];
            if (item?.role === "assistant" && item.kind === undefined) {
              const next = [...previous];
              next[index] = { ...item, duration };
              return next;
            }
          }
          return previous;
        });
      }
      setElapsed(duration);
      setBusy(false);
      setStatus(nextStatus);
      busyStart.current = null;
    },
    [],
  );

  const appendTool = useCallback(
    (kind: "tool" | "tool-result", text: string, ok = true) => {
      setMessages((previous) => [
        ...previous.slice(-199),
        { id: nextId.current++, role: "system", text, kind, ok },
      ]);
    },
    [],
  );

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
      if (name === "/init" || name === "/review" || name === "/diff") {
        append("system", `已完成 ${name}`);
        return;
      }
      append("system", `${name}: ${JSON.stringify(data)}`);
    },
    [append, exit],
  );

  const handleMessage = useCallback(
    (message: AgentMessage) => {
      switch (message.type) {
        case "chat_delta":
          stream.current += message.text;
          setMessages((previous) => {
            const last = previous[previous.length - 1];
            if (last?.role === "assistant") {
              return [...previous.slice(0, -1), { ...last, text: stream.current }];
            }
            return [
              ...previous,
              { id: nextId.current++, role: "assistant", text: stream.current },
            ];
          });
          break;
        case "chat_done":
          if (message.text && !stream.current) append("assistant", message.text);
          stream.current = "";
          finishBusy();
          break;
        case "command_result":
          handleCommandResult(message.name, message.data);
          finishBusy();
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
          append("assistant", message.markdown);
          finishBusy();
          break;
        case "error":
          append("system", message.message);
          finishBusy("出错");
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
          setStatus(`会话 ${String(message.data.session ?? "main")}`);
          break;
        case "tool_call":
          setStatus(`${message.name}(${formatArgs(message.args)})`);
          appendTool("tool", `${message.name}(${formatArgs(message.args)})`);
          break;
        case "tool_result":
          setStatus(`${message.name} → ${message.summary}`);
          appendTool("tool-result", `${message.name} → ${message.summary}`, message.ok);
          break;
        default:
          break;
      }
    },
    [append, appendTool, finishBusy, handleCommandResult],
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
      if (!text || busy) return;
      setInput("");
      setSelected(-1);
      if (text === "/quit") {
        setBusy(true);
        bridge.current?.sendCommand("/quit");
        return;
      }
      if (text === "/login") {
        setLoginError("");
        setScreen("login");
        return;
      }
      if (text.startsWith("/") && CONFIRM_COMMANDS.has((text.split(/\s+/)[0] ?? "").toLowerCase())) {
        setConfirming((text.split(/\s+/)[0] ?? "").toLowerCase());
        return;
      }
      if (text.startsWith("/")) {
        const [name, ...rest] = text.split(/\s+/);
        setBusy(true);
        bridge.current?.sendCommand(name ?? "", parseCommandArgs(name ?? "", rest));
        return;
      }
      append("user", text);
      stream.current = "";
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
        setBusy(true);
        bridge.current?.sendCommand("/quit");
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
      <Header taskTitle="Exhibit Chat" repoPath={repoPath} model={model} />
      <Box height={1} />
      <PlanBanner active={planMode} />
      {screen === "login" || screen === "login-busy" ? (
        <LoginDialog
          onCancel={() => setScreen("chat")}
          onSubmit={finishLogin}
          busy={screen === "login-busy"}
          error={loginError}
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
        <ChatView
          messages={messages}
          input={input}
          status={status}
          planMode={planMode}
          busy={busy}
          selected={selected}
          elapsed={elapsed}
        />
      )}
      {screen !== "chat" ? <Text color={theme.muted}>Esc 返回 · Ctrl+C 退出</Text> : null}
    </Box>
  );
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
