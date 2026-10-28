import { describe, expect, it } from "vitest";
import { LOGIN_PROVIDERS } from "./LoginDialog.js";

describe("login providers", () => {
  it("includes OpenRouter in the selector", () => {
    expect(LOGIN_PROVIDERS).toContainEqual({
      key: "openrouter",
      label: "OpenRouter",
    });
  });
});
