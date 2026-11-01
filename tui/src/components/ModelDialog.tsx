import React, { useState } from "react";
import { Box, Text, useInput } from "ink";
import { theme } from "../theme.js";
import {
  initialModelSelection,
  modelRows,
  moveModelSelection,
  windowAround,
  type ModelCatalog,
} from "../models.js";
import { displayWidth, truncate, truncateLeft } from "../text.js";
import { useTerminalSize } from "../useTerminalSize.js";

const VISIBLE_ROWS = 10;

export function ModelDialog({
  catalog,
  busy = false,
  error = "",
  onCancel,
  onRetry,
  onSelect,
}: {
  catalog: ModelCatalog;
  busy?: boolean;
  error?: string;
  onCancel: () => void;
  onRetry: () => void;
  onSelect: (provider: string, model: string) => void;
}) {
  const rows = modelRows(catalog);
  const [selected, setSelected] = useState(() => initialModelSelection(rows));
  const [manualProvider, setManualProvider] = useState<string | null>(null);
  const [manualModel, setManualModel] = useState("");
  const { start, end } = windowAround(selected, rows.length, VISIBLE_ROWS);
  const shown = rows.slice(start, end);
  // Double border + paddingX={2} costs 6 cells; keep 2 more as a margin so the
  // right border never lands on the terminal's last column and wraps.
  const width = Math.max(24, useTerminalSize().columns - 8);

  useInput((value, key) => {
    if (busy) return;
    if (manualProvider !== null) {
      if (key.escape) {
        setManualProvider(null);
        setManualModel("");
        return;
      }
      if (key.return) {
        const model = manualModel.trim();
        if (model) onSelect(manualProvider, model);
        return;
      }
      if (key.backspace || key.delete) {
        setManualModel((current) => current.slice(0, -1));
        return;
      }
      if (value && !key.ctrl && !key.meta) {
        setManualModel((current) => current + value);
      }
      return;
    }
    if (key.escape || (key.ctrl && value === "c")) {
      onCancel();
      return;
    }
    if (key.upArrow) {
      setSelected((current) => moveModelSelection(rows, current, -1));
      return;
    }
    if (key.downArrow) {
      setSelected((current) => moveModelSelection(rows, current, 1));
      return;
    }
    if (value.toLowerCase() === "r" && error) {
      onRetry();
      return;
    }
    if (!key.return) return;
    const row = rows[selected];
    if (row?.kind === "model") {
      onSelect(row.provider, row.model);
    } else if (row?.kind === "manual") {
      setManualProvider(row.provider);
      setManualModel("");
    }
  });

  return (
    <Box flexDirection="column" borderStyle="double" borderColor={theme.accent} paddingX={2}>
      <Text color={theme.accent} bold>
        /model · 选择模型
      </Text>
      <Text color={theme.muted}>仅显示已登录供应商；模型来自实时目录或安全回退清单</Text>
      <Box height={1} />
      {catalog.providers.length === 0 ? (
        <Text color={theme.warn}>尚未登录任何供应商，请先输入 /login。</Text>
      ) : (
        shown.map((row, offset) => {
          const index = start + offset;
          const active = index === selected && !busy;
          if (row.kind === "provider") {
            const source = row.source === "live" ? "实时" : "回退";
            const heading = `${row.label} · ${source}`;
            return (
              <Text key={`provider-${row.provider}`} color={theme.info} bold>
                {heading}
                {row.error ? (
                  <Text color={theme.dangerText}>
                    {" "}
                    {truncate(
                      `· ${row.error}`,
                      Math.max(8, width - displayWidth(heading) - 1),
                    )}
                  </Text>
                ) : null}
              </Text>
            );
          }
          if (row.kind === "manual") {
            return (
              <Text
                key={`manual-${row.provider}`}
                color={active ? theme.accent : theme.muted}
              >
                {active ? "❯ " : "  "}＋ 手动输入模型 ID
              </Text>
            );
          }
          // Model ids can be long; clip them so every row keeps the same
          // marker column and the box edge stays intact.
          const marker = `${active ? "❯ " : "  "}${row.current ? "●" : "○"} `;
          const suffix = row.current ? " · 当前" : "";
          return (
            <Text
              key={`${row.provider}-${row.model}`}
              color={active ? theme.accent : theme.text}
            >
              {marker}
              {truncate(row.model, width - marker.length - suffix.length)}
              {row.current ? <Text color={theme.muted}>{suffix}</Text> : null}
            </Text>
          );
        })
      )}
      <Box height={1} />
      {manualProvider !== null ? (
        <Box flexDirection="column">
          <Text color={theme.text}>
            {manualProvider} 模型 ID:{" "}
            <Text color={theme.accent}>
              {manualModel}
              <Text color={theme.accent}>▌</Text>
            </Text>
          </Text>
          <Text color={theme.muted}>输入准确模型 ID · Enter 应用 · Esc 返回列表</Text>
        </Box>
      ) : (
        <Text color={theme.muted}>
          {rows.length > VISIBLE_ROWS
            ? `↑↓ 选择 · ${selected + 1}/${rows.length} · Enter 应用 · Esc 取消`
            : "↑↓ 选择 · Enter 应用 · Esc 取消"}
        </Text>
      )}
      {busy ? <Text color={theme.accent}>正在切换模型…</Text> : null}
      {error ? (
        <Text color={theme.dangerText}>
          {truncate(error, Math.max(8, width - 12))} · r 重新发现
        </Text>
      ) : null}
    </Box>
  );
}

