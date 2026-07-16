# GitHub Release Checklist

Use this checklist before publishing EasySourceFlow or pushing a security-sensitive repository update. Publish through Git; never upload the whole local folder manually.

## 1. Define the Public File Set

Check the worktree and ignored files:

```bash
git status --short --ignored
git diff --check
git diff --cached --check
```

Confirm `.gitignore` excludes `.env`, runtime directories, backups, outputs, databases, logs, cookies, media, models, and secrets while preserving `.env.example`. Inspect staged files with `git status --short` and `git diff --cached` before committing.

Examples and tests must use obvious placeholders such as `EXAMPLE_API_KEY` or `test-model-api-key`.

Check commit metadata before creating a public commit:

```bash
git config user.name
git config user.email
```

Use a project or organization identity when personal attribution is not intended. Commit author names and email addresses are public Git history metadata even when file contents are clean.

## 2. Scan Secrets and Local Traces

Scan all reachable Git history with redacted output:

```bash
gitleaks git . --redact
```

Scan the public file set for credentials, private paths, workspace names, and personal service identifiers. Never print a complete suspected secret in logs or chat.

To inspect uncommitted public files without scanning the real local `.env`, stage the intended files and export the index:

```bash
public_tree="$(mktemp -d)"
git checkout-index --all --prefix="$public_tree/"
gitleaks dir "$public_tree" --redact --no-banner
```

Remove the temporary directory after the scan. Do not run an unrestricted directory scan over ignored local runtime data.

## 3. Verify Before Push

Run the checks appropriate to the change, including:

```bash
PYTHONPATH=src .venv/bin/python -m compileall -q src tests
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
.venv/bin/ruff check src tests
zsh -n scripts/easysourceflow
```

For workflow changes, parse the YAML and confirm full-history checkout uses `fetch-depth: 0`. Pin downloaded security tools and validate their checksums.

## 4. Decide the Release Boundary

`CHANGELOG.md` 的“未发布”表示代码可以已经进入 `main`，但尚未归属到版本标签和 GitHub Release。不要把标签创建后的改动反向追加到旧版本说明。

- `PATCH`：仅包含向后兼容的缺陷修复。
- `MINOR`：增加向后兼容的用户能力，或完成一组可独立交付的体验升级。
- `MAJOR`：包含不兼容的公共接口、配置或数据格式变化；`1.0.0` 之前仍需在发布说明中明确兼容影响。

普通开发提交不要求逐次发布。稳定的用户可见能力或一组完整修复进入 `main`、测试和文档完成后，应明确决定下一个语义化版本，不应长期只保留在“未发布”。

## 5. Publish a Version

EasySourceFlow follows semantic versioning. The single version source is `src/easysourceflow_core/__init__.py`; package metadata, HTTP, and MCP read it automatically.

Before publishing a release:

1. Update `__version__` and the version badge in `README.md`.
2. Add a dated entry to `CHANGELOG.md` and update the matching milestone in `docs/ROADMAP.md`.
3. Run all release checks and commit the release changes.
4. Create an annotated tag such as `git tag -a vX.Y.Z -m "EasySourceFlow vX.Y.Z"`.
5. Push the commit and tag, then create a GitHub Release from that tag.
6. Verify that the Release page, tag, changelog, and CI all show the same version.

Do not reuse or move an existing public version tag. Fix a released version with a new patch version instead.

## 6. Push and Verify the Remote

- Confirm the GitHub account, repository, visibility, and default branch.
- Push only after local scans and tests pass.
- Confirm local and remote commit hashes match.
- Verify GitHub Actions tests and the Gitleaks job succeed.
- Inspect the remote tree to confirm private and ignored files are absent.
- Do not install or use GitHub plugins without user approval.

## 7. History Rewrite Procedure

Rewrite public history only when necessary and only after explicit user approval.

1. Check forks, pull requests, releases, branches, tags, and collaborator activity.
2. Record the expected remote commit so concurrent updates cannot be overwritten.
3. Create a private Git bundle with mode `600` for recovery.
4. Build the sanitized history in an isolated bundle or clone. A Git worktree shares refs and may store an absolute path in its `.git` file, so it is not sufficient isolation for this check.
5. Run Gitleaks, local-trace scans, tests, and static checks against the isolated history.
6. Push with `git push --force-with-lease`; never use plain `--force`.
7. Verify the new remote CI run before deleting old workflow runs or local recovery refs.
8. Clean local reflogs and unreachable objects, then validate with a fresh clone.

GitHub may temporarily retain unreachable objects addressable by their old SHA. Report this limitation; contact GitHub Support only when immediate removal is required for genuinely sensitive data.

## 8. Shell and Verification Pitfalls

- Check each command's exit status; do not let a later successful command hide an earlier failure.
- In zsh, do not use `path` as a loop variable because it changes the command search path.
- `rg` exits with status `1` when it finds no matches; treat that as a successful clean scan when appropriate.
- Distinguish network/download failures from a completed security scan.
- Report only checks that actually ran and state any remaining uncertainty.
