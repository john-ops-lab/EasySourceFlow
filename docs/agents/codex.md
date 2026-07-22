# Codex 接入

Codex CLI、IDE 扩展和桌面端在同一 Codex 主机上共享 MCP 配置。

## 1. 注册 MCP

```bash
codex mcp add easysourceflow \
  --env EASYSOURCEFLOW_BASE_URL=http://127.0.0.1:8765 \
  -- "<PROJECT_ROOT>/.venv/bin/easysourceflow-mcp"

codex mcp list
```

也可以在 Codex 的 `config.toml` 中配置 `[mcp_servers.easysourceflow]`。模型 API Key 仍由 EasySourceFlow 管理，不要写进 Codex 配置。

## 2. 安装 Skill

安装为当前用户可用的 Skill：

```bash
scripts/easysourceflow install-skill --client codex "$HOME"
```

文件会进入 `~/.agents/skills/easysourceflow/`。如只希望当前仓库使用，可把仓库根目录作为最后一个参数，安装到 `<repo>/.agents/skills/easysourceflow/`。

安装后新建一个 Codex 任务，再发送文章链接进行验收。确认工具列表包含 EasySourceFlow，并且最终回复没有二次总结。

上游参考：[Codex MCP](https://developers.openai.com/codex/mcp) · [Codex Skills](https://developers.openai.com/codex/skills)
