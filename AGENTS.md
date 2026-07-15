# Repository Guidelines

## Project Structure & Module Organization

EasySourceFlow is a Python 3.9+ local content summarization service with HTTP, Web UI, and MCP entry points.

- `src/easysourceflow_core/`: core daemon, HTTP API, Web UI, extractors, digest generation, SQLite store, output writing, backup, cleanup, and maintenance logic.
- `src/easysourceflow_core/extractors/`: source-specific extraction for web pages, WeChat articles, and video platforms.
- `src/easysourceflow_mcp/`: stdio MCP adapter used by agents.
- `tests/`: `unittest` coverage for core behavior, HTTP API, and MCP formatting.
- `docs/`: requirements, architecture, operations, deployment, test plan, security notes, and ADRs.
- `scripts/easysourceflow`: local service, launchd, backup, cleanup, and regression helper commands.
- `var/` and `backup/`: local runtime artifacts; avoid committing generated logs or sensitive outputs.

## Build, Test, and Development Commands

```bash
cp .env.example .env
PYTHONPATH=src python3 -m compileall -q src tests
PYTHONPATH=src python3 -m unittest discover -s tests -v
scripts/easysourceflow start
scripts/easysourceflow open
scripts/easysourceflow health
scripts/easysourceflow regression
scripts/easysourceflow install-launchd
```

Use `compileall` for syntax checks, `unittest` for the main test suite, `start/open` for local Web UI testing, `health` for dependency checks, and `regression` for smoke validation.

## Coding Style & Naming Conventions

Use 4-space indentation and standard Python naming: `snake_case` for functions and modules, `PascalCase` for classes, and uppercase constants. Keep changes surgical and match nearby style. Prefer structured helpers over ad hoc string parsing when handling JSON, URLs, Markdown, or paths. Do not log API keys, cookies, full `.env` contents, or sensitive source text.

## Testing Guidelines

Tests use Python `unittest`. Add focused tests near related coverage in `tests/test_core.py` or `tests/test_http_and_mcp.py`. Test names should describe behavior, for example `test_list_outputs_hides_resource_timeline`. Run the full suite before handing off changes:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

## Commit & Pull Request Guidelines

Use concise imperative commit messages such as `Add model configuration form` or `Fix Bilibili cookie status`. Pull requests should include the problem, implementation summary, verification commands, and screenshots for Web UI changes. Link related docs or issues when applicable.

## Security & Configuration Tips

Keep secrets in `.env` or the launchd runtime config, never in docs, tests, logs, or chat output. Bilibili cookies and `DEEPSEEK_API_KEY` are credentials. Validate local Web changes at `http://127.0.0.1:8765/` and avoid exposing the service beyond localhost unless explicitly required.

## GitHub Publishing

- Follow `docs/RELEASE_CHECKLIST.md` before publishing or pushing repository changes.
- Never publish credentials, cookies, `.env`, databases, logs, outputs, backups, or private workspace data.
- Run Gitleaks with redacted output and scan staged public files for local paths and personal identifiers.
- Verify the exact staged file set before committing and confirm GitHub Actions after pushing.
- Never rewrite shared history or force-push without explicit user approval. For an approved rewrite, use `--force-with-lease`, never plain `--force`.
