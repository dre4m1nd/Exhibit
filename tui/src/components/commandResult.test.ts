import { describe, expect, it } from "vitest";
import { describeCommandResult } from "./App.js";

describe("describeCommandResult surfaces every command result", () => {
  it("echoes /logout removal", () => {
    expect(describeCommandResult("/logout", { removed: true, provider: "deepseek" })).toBe(
      "已退出登录 deepseek",
    );
  });

  it("echoes /clear", () => {
    expect(describeCommandResult("/clear", { cleared: true })).toBe("对话上下文已清空");
  });

  it("echoes /compact with kept messages and files", () => {
    expect(
      describeCommandResult("/compact", { messages: 2, changed_files: ["a.py", "b.ts"] }),
    ).toBe("已压缩上下文，保留 2 条，文件变更：a.py, b.ts");
  });

  it("echoes /compact with no files", () => {
    expect(describeCommandResult("/compact", { messages: 1, changed_files: [] })).toBe(
      "已压缩上下文，保留 1 条，文件变更：无",
    );
  });

  it("echoes /permissions", () => {
    expect(
      describeCommandResult("/permissions", {
        mode: "agent",
        writes: true,
        confirmation: "each_write",
      }),
    ).toBe("模式 agent · 写入权限 开启 · 确认策略 each_write");
  });

  it("echoes /files with read and changed lists", () => {
    expect(
      describeCommandResult("/files", { read_files: ["README.md"], changed_files: ["x.py"] }),
    ).toBe("已读 README.md · 已改 x.py");
  });

  it("echoes /files when empty", () => {
    expect(describeCommandResult("/files", { read_files: [], changed_files: [] })).toBe(
      "已读 无 · 已改 无",
    );
  });

  it("echoes a successful /undo with the path", () => {
    expect(describeCommandResult("/undo", { undone: "src/app.py" })).toBe(
      "已撤销：src/app.py",
    );
  });

  it("echoes when there is nothing to undo", () => {
    expect(describeCommandResult("/undo", { undone: null })).toBe("没有可撤销的修改");
  });

  it("echoes /commands as a prefixed list", () => {
    expect(
      describeCommandResult("/commands", {
        commands: [
          { name: "/status", description: "查看当前会话状态" },
          { name: "/plan", description: "进入或退出计划模式" },
        ],
      }),
    ).toBe(
      "可用命令：\n/status · 查看当前会话状态\n/plan · 进入或退出计划模式",
    );
  });

  it("never renders command objects as [object Object]", () => {
    const text = describeCommandResult("/commands", {
      commands: [{ name: "/files", description: "查看本轮读取或修改的文件" }],
    });
    expect(text).not.toContain("[object Object]");
    expect(text).toContain("/files · 查看本轮读取或修改的文件");
  });

  it("handles a bare /commands result", () => {
    expect(describeCommandResult("/commands", { commands: [] })).toBe("没有可用命令");
  });

  it("echoes unknown commands as JSON rather than dropping them", () => {
    expect(describeCommandResult("/mystery", { ok: 1 })).toBe('/mystery: {"ok":1}');
  });

  it("does not drop any known command result (smoke over the catalog)", () => {
    const samples: Record<string, Record<string, unknown>> = {
      "/logout": { removed: true, provider: "openai" },
      "/clear": { cleared: true },
      "/compact": { messages: 0, changed_files: [] },
      "/permissions": { mode: "plan", writes: false, confirmation: "none" },
      "/files": { read_files: [], changed_files: [] },
      "/undo": { undone: null },
      "/commands": { commands: [] },
    };
    for (const [name, data] of Object.entries(samples)) {
      expect(describeCommandResult(name, data)).not.toBe("");
    }
  });
});
