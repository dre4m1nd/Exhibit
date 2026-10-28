/** Model catalog rows and navigation shared by the selector and tests. */

import { windowAround } from "./commands.js";

export { windowAround };

export interface ModelProviderGroup {
  key: string;
  label: string;
  source: "live" | "fallback";
  error: string;
  models: string[];
}

export interface ModelCatalog {
  current: {
    provider: string;
    model: string;
  };
  providers: ModelProviderGroup[];
}

export type ModelRow =
  | {
      kind: "provider";
      provider: string;
      label: string;
      source: "live" | "fallback";
      error: string;
    }
  | {
      kind: "model";
      provider: string;
      label: string;
      model: string;
      current: boolean;
    }
  | {
      kind: "manual";
      provider: string;
      label: string;
    };

function strings(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string");
}

/** Convert an untrusted protocol payload into a typed model catalog. */
export function parseModelCatalog(data: Record<string, unknown>): ModelCatalog | null {
  if (data.kind !== "model_catalog" || !Array.isArray(data.providers)) return null;
  const current =
    typeof data.current === "object" && data.current !== null
      ? (data.current as Record<string, unknown>)
      : {};
  const provider = typeof current.provider === "string" ? current.provider : "";
  const model = typeof current.model === "string" ? current.model : "";
  const providers: ModelProviderGroup[] = [];
  for (const value of data.providers) {
    if (typeof value !== "object" || value === null) continue;
    const item = value as Record<string, unknown>;
    const key = typeof item.key === "string" ? item.key : "";
    if (!key) continue;
    providers.push({
      key,
      label: typeof item.label === "string" && item.label ? item.label : key,
      source: item.source === "live" ? "live" : "fallback",
      error: typeof item.error === "string" ? item.error : "",
      models: strings(item.models),
    });
  }
  return { current: { provider, model }, providers };
}

/** Flatten groups into headers, selectable models, and manual-entry actions. */
export function modelRows(catalog: ModelCatalog): ModelRow[] {
  const rows: ModelRow[] = [];
  for (const provider of catalog.providers) {
    rows.push({
      kind: "provider",
      provider: provider.key,
      label: provider.label,
      source: provider.source,
      error: provider.error,
    });
    for (const model of provider.models) {
      rows.push({
        kind: "model",
        provider: provider.key,
        label: provider.label,
        model,
        current:
          catalog.current.provider === provider.key &&
          catalog.current.model === model,
      });
    }
    rows.push({
      kind: "manual",
      provider: provider.key,
      label: provider.label,
    });
  }
  return rows;
}

export function isSelectableRow(row: ModelRow | undefined): boolean {
  return row?.kind === "model" || row?.kind === "manual";
}

/** Prefer the active model, then the first actionable row. */
export function initialModelSelection(rows: ModelRow[]): number {
  const current = rows.findIndex((row) => row.kind === "model" && row.current);
  if (current >= 0) return current;
  return rows.findIndex(isSelectableRow);
}

/** Move through actionable rows only, wrapping at either end. */
export function moveModelSelection(
  rows: ModelRow[],
  current: number,
  delta: number,
): number {
  const selectable = rows
    .map((row, index) => (isSelectableRow(row) ? index : -1))
    .filter((index) => index >= 0);
  if (selectable.length === 0) return -1;
  const position = selectable.indexOf(current);
  const start = position >= 0 ? position : 0;
  const next = (((start + delta) % selectable.length) + selectable.length) % selectable.length;
  return selectable[next] ?? -1;
}

