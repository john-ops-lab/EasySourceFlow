# Agent 接入指南

EasySourceFlow 面向 Agent 提供两层集成：MCP 负责稳定的工具调用，官方 Skill 负责调用时机和结果交付规则。核心提取、字幕、ASR、总结和文件处理始终由本地服务完成。

Web 控制台的“维护 → Agent 接入”提供可复制的 MCP 配置、Skill 安装命令和接入状态。状态页会区分组件已就绪与最近实际收到过 MCP 调用。
页面中的 MCP 命令使用 `<PROJECT_ROOT>` 占位符；只在本机 Agent 配置中替换真实路径，不要把替换后的绝对路径提交到仓库。

## 1. 启动服务

```bash
scripts/easysourceflow start
scripts/easysourceflow health
```

服务默认只监听 `127.0.0.1:8765`。

## 2. 配置 MCP

MCP 客户端应以 stdio 方式启动：

```text
<repo>/.venv/bin/easysourceflow-mcp
```

如果服务不在默认地址，给 MCP 进程设置：

```text
EASYSOURCEFLOW_BASE_URL=http://127.0.0.1:8765
```

不同 Agent 的配置文件格式不同，但 command 应指向上述可执行文件，不需要把模型 API Key 写进 Agent 配置。

## 3. 安装官方 Skill

把 Skill 安装到 Agent 工作区：

```bash
scripts/easysourceflow install-skill "$AGENT_WORKSPACE"
```

先把 `AGENT_WORKSPACE` 设置为目标 Agent 的工作区路径。安装后文件位于：

```text
<agent-workspace>/skills/easysourceflow/SKILL.md
```

Skill 规定所有单链接默认使用可恢复的异步流程、视频默认使用 Pro、最终 Markdown 原样交付、不得二次总结，以及用户回复“收藏”时收藏最近结果。

正常提交保持 `force_refresh=false` 以复用仍有效的缓存。只有用户明确要求重新抓取、重新转写、重新生成或忽略旧结果时才传 `true`；任务重试默认强制刷新。

## 4. 单链接调用流程

1. 调用 `easysourceflow_submit_link` 并保存 `job_id`。
2. 使用同一 `job_id` 调用 `easysourceflow_get_job`，建议传 `wait_seconds=45`。
3. 如果状态仍为 `queued` 或 `running`，继续查询；不要改用网页抓取、浏览器或 Agent 自身模型生成替代总结。
4. 仅在 `succeeded` 且存在 `result.summary_markdown` 时，将 Markdown 原样交付。
5. 如果任务失败或取消，只转达服务返回的错误和处理建议。

`easysourceflow_summarize_link` 仅保留给旧调用方兼容短的非视频网页，不是 Agent 新请求的默认入口。

## 5. 验收

依次让 Agent 完成：

1. 总结普通文章链接，并原样返回 Markdown。
2. 总结视频链接，确认任务使用 Pro 且结果标出字幕来源。
3. 在收到结果后回复“收藏”，确认只收藏当前结果且不重复发送全文。

完整工具契约见 [MCP_API.md](MCP_API.md)。Skill 的测试场景位于 `skills/easysourceflow/evals/evals.json`。
