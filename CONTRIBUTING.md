# Contributing

Thanks for improving EasySourceFlow. Keep changes small, testable, and local-first.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env
```

Fill `.env` with local-only values. Do not commit API keys, cookies, logs, SQLite files, generated outputs, downloaded media, or model files.

## Development

Run the local service:

```bash
scripts/easysourceflow start
scripts/easysourceflow open
```

Run checks before opening a pull request:

```bash
PYTHONPATH=src .venv/bin/python -m compileall -q src tests
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
.venv/bin/ruff check src tests
```

Before publishing or pushing security-sensitive changes, follow [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md).

## Pull Requests

- Describe the user-facing behavior change.
- Link related issues when available.
- Include screenshots for Web UI changes.
- Add or update tests for extractor, queue, MCP, HTTP, or output-format changes.
- Keep unrelated refactors out of the PR.

## Extractors

Extractor changes should preserve source metadata, avoid leaking cookies or headers, and surface fallback behavior clearly. If a feature silently falls back from platform subtitles to local ASR, record that in metadata and user-facing output.
