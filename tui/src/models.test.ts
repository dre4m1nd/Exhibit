import { describe, expect, it } from "vitest";
import {
  initialModelSelection,
  modelRows,
  moveModelSelection,
  parseModelCatalog,
  type ModelCatalog,
} from "./models.js";

const catalog: ModelCatalog = {
  current: { provider: "deepseek", model: "deepseek-chat" },
  providers: [
    {
      key: "deepseek",
      label: "DeepSeek",
      source: "live",
      error: "",
      models: ["deepseek-chat", "deepseek-reasoner"],
    },
    {
      key: "qwen",
      label: "Qwen",
      source: "fallback",
      error: "模型列表请求超时",
      models: ["qwen-plus"],
    },
  ],
};

describe("model catalog", () => {
  it("parses only logged-in provider groups from the protocol payload", () => {
    const parsed = parseModelCatalog({
      kind: "model_catalog",
      current: catalog.current,
      providers: catalog.providers,
    });

    expect(parsed).toEqual(catalog);
    expect(parseModelCatalog({ kind: "model_selected" })).toBeNull();
  });

  it("flattens provider headers, models, and manual rows", () => {
    expect(modelRows(catalog).map((row) => row.kind)).toEqual([
      "provider",
      "model",
      "model",
      "manual",
      "provider",
      "model",
      "manual",
    ]);
  });

  it("defaults to the current model and otherwise the first model", () => {
    const rows = modelRows(catalog);
    expect(initialModelSelection(rows)).toBe(1);
    expect(
      initialModelSelection(
        modelRows({
          current: { provider: "openai", model: "missing" },
          providers: catalog.providers,
        }),
      ),
    ).toBe(1);
  });

  it("moves only between models and manual actions with wrapping", () => {
    const rows = modelRows(catalog);
    expect(moveModelSelection(rows, 1, 1)).toBe(2);
    expect(moveModelSelection(rows, 3, 1)).toBe(5);
    expect(moveModelSelection(rows, 6, 1)).toBe(1);
    expect(moveModelSelection(rows, 1, -1)).toBe(6);
  });

  it("falls back to manual entry when a provider has no models", () => {
    const rows = modelRows({
      current: { provider: "", model: "" },
      providers: [
        {
          key: "empty",
          label: "Empty",
          source: "fallback",
          error: "",
          models: [],
        },
      ],
    });
    expect(initialModelSelection(rows)).toBe(1);
    expect(moveModelSelection(rows, -1, 1)).toBe(1);
  });
});

