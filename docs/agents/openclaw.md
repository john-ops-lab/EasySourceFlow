# OpenClaw 接入

本文适用于支持原生 `openclaw mcp` 和 `openclaw skills` 命令的新版 OpenClaw，最后按 `2026.7.1-2` CLI 核对。

## 1. 预检

```bash
node --version
openclaw --version
openclaw config validate
```

如果 `openclaw --version` 已因 Node 版本报错，先按当前 OpenClaw 安装器提示切换到受支持的 Node 版本，再继续。不要把 CLI 运行时错误误判为 EasySourceFlow MCP 故障。

## 2. 注册 MCP

在 EasySourceFlow 项目目录执行，并替换项目路径：

```bash
openclaw mcp add easysourceflow \
  --command "<PROJECT_ROOT>/.venv/bin/easysourceflow-mcp" \
  --env EASYSOURCEFLOW_BASE_URL=http://127.0.0.1:8765

openclaw mcp doctor easysourceflow --probe
```

`mcp add` 会先探测再保存；`doctor --probe` 应确认服务能启动并列出工具。OpenClaw 默认热加载 `mcp` 配置，通常不需要手工重启 Gateway。

## 3. 安装 Skill

推荐使用 OpenClaw 原生命令：

```bash
openclaw skills install "<PROJECT_ROOT>/skills/easysourceflow" --agent <agent-id> --force
openclaw skills check
```

也可使用仓库兼容脚本：

```bash
scripts/easysourceflow install-skill --client openclaw <agent-workspace>
```

当前 Skill 位于仓库子目录，不能直接使用 `openclaw skills install git:john-ops-lab/EasySourceFlow`，因为 Git 安装要求源目录根部存在 `SKILL.md`。

## 4. 白名单和会话

如果配置了 `agents.defaults.skills` 或 `agents.list[].skills`，确认目标 Agent 的最终列表包含 `easysourceflow`：

```bash
openclaw config get agents.list --json
```

省略 Agent 自己的 `skills` 时会继承默认列表；非空 Agent 列表会替换默认列表而不是合并，修改时必须保留原有 Skill。

安装或更新 Skill 后，在目标聊天中单独发送：

```text
/new
```

`/new` 用于建立新会话并刷新 Skill 快照。只有配置未热加载、Gateway 运行异常或诊断明确要求时才执行 `openclaw gateway restart`。

## 5. 附件和验收

OpenClaw 标准入站附件目录默认被 EasySourceFlow 允许。自定义附件目录时，在 MCP 环境中设置 `EASYSOURCEFLOW_DOCUMENT_IMPORT_ROOTS`。

最终检查：

```bash
openclaw mcp status --verbose
openclaw mcp doctor easysourceflow --probe
openclaw skills check
```

然后在新会话发送一个文章链接，确认 Agent 调用 `easysourceflow_submit_link`，并把最终 Markdown 原样返回。

上游参考：[OpenClaw MCP](https://docs.openclaw.ai/cli/mcp) · [OpenClaw Skills](https://docs.openclaw.ai/skills) · [配置热加载](https://docs.openclaw.ai/gateway/configuration)
