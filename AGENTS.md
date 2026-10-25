# Repository Guidelines

## Project Structure & Module Organization

Exhibit is a terminal agent: Python (AgentScope 2.x) runs the reasoning loop, Node/React-Ink
renders the TUI, and both talk over stdio JSON lines.

- `agent/` — `app.py` (stdio entrypoint), `agents.py` (ReAct agent),
  `prompt_loader.py`, `config.py`, `protocol.py`, `tools/fs.py`, `tools/git.py`
- `agent/prompts/` — editable Markdown system prompts, shared report rules, and the
  user-prompt template; set `EXHIBIT_PROMPT_DIR` to use another complete prompt set
- `tui/src/` — `main.tsx`, `bridge.ts` (subprocess + protocol), `theme.ts`, `components/`
- `examples/fixture-repo/` — sample repo for tests and smoke runs
- `tests/` — pytest suites; `任务规划书.md` — Chinese planning doc

## Build, Test, and Development Commands

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd tui; npm install; cd ..

.\Exhibit.ps1                                                  # run the TUI
.\.venv\Scripts\python.exe -m agent.app --task arch_overview --repo-path .   # headless
.\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider            # Python tests
cd tui; node node_modules\typescript\bin\tsc -p tsconfig.json --noEmit       # typecheck
cd tui; node node_modules\vitest\vitest.mjs run                              # TUI tests
```

## Coding Style & Naming Conventions

- Python: 4-space indent, type hints on public functions, `ruff` (line length 88).
- Prompts: keep each task's wording in `agent/prompts/*.md`; avoid re-adding inline prompts.
- TypeScript/React: 2-space indent, functional components, `PascalCase.tsx` components,
  `camelCase.ts` modules, named exports only.
- JSON line event keys are snake_case and must mirror `agent/protocol.py`.
- Keep functions under ~40 lines; prefer early returns over nesting.

## Testing Guidelines

- `pytest tests/` covers tools, protocol encoding, and prompt loading/rendering.
  New tools need a fixture-repo test; prompt changes need a `tests/test_prompts.py` case.
- Vitest specs live in `tui/src/**/*.test.ts`; every protocol event type needs a case.
- Use the repo-local `tmp_path` fixture in `tests/test_tools.py`; the OS temp dir is restricted.

## Commit & Pull Request Guidelines

Use Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`). PRs must state
intent, link issues, and list manual verification (one task run plus a narrow-terminal check).

## Security & Configuration Tips

- Never commit `.venv/`, `tui/node_modules/`, `tui/dist/`, or `__pycache__/`.
- Keys belong in environment variables, never in source; `.env` is git-ignored.
- Model calls require `EXHIBIT_API_KEY`; local/private endpoints are rejected.
- Agent tools are read-only; keep them that way unless a task explicitly needs writes.
