# Exhibit

Exhibit 是一个终端智能体：用 Python（AgentScope 2.x）做推理与真实工具调用，用
React-Ink 渲染终端界面，两者通过 stdio 上的 JSON 行协议通信。

## 四个能力

| 任务 | 说明 |
| --- | --- |
| 架构总览与模块职责 | 模块划分、依赖关系、职责说明、阅读路径 |
| 架构失职审查 | 越层调用、循环依赖、职责失衡、隐式约定 |
| 整仓代码审查 | 正确性、健壮性、安全、可维护性、测试缺口 |
| Git 变更审查 | 未提交改动 / commit range / 分支 diff |

## 快速开始

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd tui; npm install; cd ..
.\Exhibit.ps1
```

不带 TUI、直接跑一次任务（输出 JSON 事件流）：

```powershell
.\.venv\Scripts\python.exe -m agent.app --task arch_overview --repo-path examples/fixture-repo
```

## 配置

复制 `.env.example` 里的变量到环境变量即可覆盖默认值：

- `EXHIBIT_BASE_URL`：远程 OpenAI 兼容 API，默认 `https://api.openai.com/v1`；
  必须是 HTTPS，且不能是本机或私网地址
- `EXHIBIT_API_KEY`：必填；未设置时程序拒绝启动
- `EXHIBIT_MODEL`：默认 `gpt-5.4-mini`
- `EXHIBIT_MAX_ITERS`：ReAct 循环上限，默认 60
- `EXHIBIT_PROMPT_DIR`：自定义提示词目录，默认 `agent/prompts/`

系统提示词位于 `agent/prompts/*.md`，可直接编辑；`report_rules.md` 会追加到每类任务后。
用户提示词模板位于 `agent/prompts/user_prompt.md`，支持 `{{repo_path}}` 与
`{{scope_line}}` 占位符。自定义目录必须包含全部提示词文件。

## 开发

```powershell
# Python 测试
.\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider

# TUI 类型检查与测试
cd tui
node node_modules\typescript\bin\tsc -p tsconfig.json --noEmit
node node_modules\vitest\vitest.mjs run
```

## 目录

```
agent/            Python 智能体（AgentScope ReAct + 工具）
  app.py          stdio 入口，转发事件
  prompts/        任务提示词与用户提示词模板（Markdown）
  prompt_loader.py  提示词加载与模板渲染
  protocol.py     JSON 行协议
  tools/          文件系统与 git 工具
tui/              React-Ink 终端界面
examples/         测试用样例仓库（内含未提交改动）
tests/            Python 单测
```

## 说明

- 工具只读：文件系统与 git 工具都不会修改目标仓库。
- 报告默认中文，按「高 / 中 / 低」分级并给出 `文件:行号`。
- 在报告页按 `s` 保存为 `EXHIBIT_REPORT.md`，按 `q` 返回菜单。
