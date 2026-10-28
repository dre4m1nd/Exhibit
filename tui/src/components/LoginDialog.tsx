import React, { useState } from "react";
import { Box, Text, useInput } from "ink";
import { theme } from "../theme.js";

export interface LoginRequest {
  provider: string;
  apiKey: string;
  model: string;
  baseUrl: string;
}

export const LOGIN_PROVIDERS = [
  { key: "openai", label: "OpenAI" },
  { key: "deepseek", label: "DeepSeek" },
  { key: "qwen", label: "Qwen" },
  { key: "openrouter", label: "OpenRouter" },
  { key: "custom", label: "自定义 OpenAI 兼容端点" },
];

type Field = "provider" | "key" | "baseUrl" | "model";
const FIELDS: Field[] = ["provider", "key", "baseUrl", "model"];

export function LoginDialog({
  onCancel,
  onSubmit,
  busy = false,
  error = "",
}: {
  onCancel: () => void;
  onSubmit: (request: LoginRequest) => void;
  busy?: boolean;
  error?: string;
}) {
  const [providerIndex, setProviderIndex] = useState(0);
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [field, setField] = useState<Field>("provider");
  const provider = LOGIN_PROVIDERS[providerIndex]!;
  const isCustom = provider.key === "custom";

  const fieldValue = (target: Field): string =>
    target === "key" ? apiKey : target === "baseUrl" ? baseUrl : model;
  const setFieldValue = (target: Field, value: string): void => {
    if (target === "key") setApiKey(value);
    else if (target === "baseUrl") setBaseUrl(value);
    else if (target === "model") setModel(value);
  };

  /** Only a custom endpoint needs Base URL and Model; known providers preset both. */
  const steps: Field[] = isCustom ? FIELDS : ["provider", "key"];
  const nextField = (current: Field): Field =>
    steps[steps.indexOf(current) + 1] ?? current;
  const previousField = (current: Field): Field =>
    steps[steps.indexOf(current) - 1] ?? current;

  useInput((input, key) => {
    if (key.ctrl && input === "c") {
      onCancel();
      return;
    }
    if (busy) return;
    if (key.escape) {
      if (field !== "provider" && fieldValue(field)) setFieldValue(field, "");
      else if (field !== "provider") setField(previousField(field));
      else onCancel();
      return;
    }
    if (field === "provider") {
      if (key.upArrow) setProviderIndex((index) => Math.max(0, index - 1));
      else if (key.downArrow) {
        setProviderIndex((index) =>
          Math.min(LOGIN_PROVIDERS.length - 1, index + 1),
        );
      } else if (key.return) setField("key");
      return;
    }
    if (key.return) {
      // Each step only validates the field it is on, so a custom endpoint can
      // still walk key -> base URL -> model without a deadlock.
      if (!fieldValue(field).trim()) return;
      const target = nextField(field);
      if (target !== field) {
        setField(target);
        return;
      }
      if (isCustom && (!baseUrl.trim() || !model.trim() || !apiKey.trim())) return;
      onSubmit({
        provider: provider.key,
        apiKey,
        model: isCustom ? model.trim() : "",
        baseUrl,
      });
      return;
    }
    if (key.backspace || key.delete) {
      setFieldValue(field, fieldValue(field).slice(0, -1));
      return;
    }
    if (input && !key.ctrl && !key.meta) setFieldValue(field, fieldValue(field) + input);
  });

  return (
    <Box flexDirection="column" borderStyle="double" borderColor={theme.accent} paddingX={2}>
      <Text color={theme.accent} bold>
        /login
      </Text>
      <Text color={theme.muted}>选择供应商，然后输入 API Key（不会显示明文）</Text>
      <Box height={1} />
      {LOGIN_PROVIDERS.map((item, index) => (
        <Text
          key={item.key}
          color={field === "provider" && index === providerIndex ? theme.accent : theme.muted}
        >
          {field === "provider" && index === providerIndex ? "❯" : " "} {item.label} ·{" "}
          {item.key === "custom" ? "需填写端点与模型" : "使用供应商默认模型"}
        </Text>
      ))}
      <Box height={1} />
      {field === "baseUrl" ? (
        <Text color={theme.text}>
          Base URL: <Text color={theme.accent}>{baseUrl}</Text>
          <Text color={theme.accent}>▌</Text>
        </Text>
      ) : null}
      {field === "model" ? (
        <Text color={theme.text}>
          Model: <Text color={theme.accent}>{model}</Text>
          <Text color={theme.accent}>▌</Text>
        </Text>
      ) : null}
      <Text color={field === "key" ? theme.text : theme.muted}>
        API Key: <Text color={theme.accent}>{"*".repeat(apiKey.length)}</Text>
        {field === "key" ? <Text color={theme.accent}>▌</Text> : null}
      </Text>
      <Text color={theme.muted}>
        {busy
          ? "正在校验 API Key…"
          : field === "provider"
            ? "↑↓ 选择 · Enter 下一步 · Esc 取消"
            : isCustom
              ? `输入 ${field === "key" ? "API Key" : field === "baseUrl" ? "Base URL" : "Model"} · Enter 继续 · Esc 后退`
              : "Enter 登录 · Esc 后退"}
      </Text>
      {error ? <Text color={theme.danger}>{error}</Text> : null}
    </Box>
  );
}
