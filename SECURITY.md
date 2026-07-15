# Security Policy

EasySourceFlow is designed as a local-first service. By default it listens on `127.0.0.1` and should not be exposed to the public internet.

## Reporting a Vulnerability

Please open a private security advisory if the repository host supports it. Otherwise, create an issue with minimal reproduction details and do not include API keys, cookies, private source content, or generated outputs.

## Sensitive Data

Never commit:

- `.env` files
- API keys
- Bilibili or YouTube cookies
- SQLite databases
- generated outputs
- logs
- downloaded audio/video
- local ASR model files

## Before Publishing

Publish from Git, not by dragging the whole project folder into a website. Ignored
local files can still be uploaded by manual folder upload.

Before pushing a public repository:

```bash
gitleaks git . --redact
git status --ignored --short
rg -n --hidden --glob '!.git/**' --glob '!SECURITY.md' \
  --glob '!.env' --glob '!.venv/**' --glob '!var/**' --glob '!backup/**' \
  --glob '!build/**' --glob '!dist/**' --glob '!*.egg-info/**' \
  "(sk-[A-Za-z0-9_-]{8,}|/Users[/]|/home/[A-Za-z0-9._-]+[/]|[A-Za-z]:.Users.|[.]openclaw|workspace-[A-Za-z0-9_-]+|io[.]github[.][A-Za-z0-9_-]+|SESSDATA)"
```

If any real key, cookie, private path, database, log, generated output, or
conversation backup appears in tracked files, remove it before publishing and
rotate the credential.

See [docs/SECURITY_PRIVACY.md](docs/SECURITY_PRIVACY.md) for the detailed threat model and privacy notes.
