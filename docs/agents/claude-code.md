# Claude Code 接入

## 1. 注册 MCP

推荐安装为当前用户可用的 stdio MCP 服务：

```bash
claude mcp add \
  --transport stdio \
  --scope user \
  --env EASYSOURCEFLOW_BASE_URL=http://127.0.0.1:8765 \
  easysourceflow -- "<PROJECT_ROOT>/.venv/bin/easysourceflow-mcp"

claude mcp list
```

进入 Claude Code 后可使用 `/mcp` 查看连接状态。项目级配置需要用户先信任项目，不要把本机绝对路径或凭据提交到公开 `.mcp.json`。

## 2. 安装 Skill

```bash
scripts/easysourceflow install-skill --client claude-code "$HOME"
```

文件会进入 `~/.claude/skills/easysourceflow/`。如只希望当前项目使用，可把项目根目录作为最后一个参数。

安装后开启新会话，提交一个文章链接，确认 Claude Code 调用 EasySourceFlow MCP 并原样返回最终 Markdown。

上游参考：[Claude Code MCP](https://code.claude.com/docs/en/mcp) · [Claude Code Skills](https://code.claude.com/docs/en/skills)
