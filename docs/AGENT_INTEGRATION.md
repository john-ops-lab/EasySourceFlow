# Agent 接入指南

EasySourceFlow 的接入分为两层：MCP 提供稳定的工具能力，官方 Skill 规定何时调用、如何等待任务以及如何原样交付结果。提取、字幕、ASR、总结、缓存和文件写入始终由本地服务完成。

## 1. 通用前提

```bash
scripts/easysourceflow start
scripts/easysourceflow health
```

MCP 客户端以 stdio 启动：

```text
<PROJECT_ROOT>/.venv/bin/easysourceflow-mcp
```

默认环境变量：

```text
EASYSOURCEFLOW_BASE_URL=http://127.0.0.1:8765
```

模型 API Key 由 EasySourceFlow Web 管理，不应写入 Agent 配置。真实项目路径只保存在本机配置中，不要提交到 Git。

## 2. 选择 Agent

不同客户端的注册命令、Skill 目录和会话刷新方式并不通用。请选择对应指南：

- [OpenClaw](agents/openclaw.md)
- [Codex](agents/codex.md)
- [Claude Code](agents/claude-code.md)
- [其他 stdio MCP 客户端](agents/generic-mcp.md)

只有能够启动本地 stdio MCP 服务的 Agent 才能直接调用 EasySourceFlow。支持 Agent Skills 标准的客户端还可以安装官方 Skill；不支持 Skill 的客户端仍可使用 MCP，但需要在客户端规则中保留下述调用约束。

| 客户端 | MCP | Skill | 接入状态 |
| --- | --- | --- | --- |
| OpenClaw | stdio | Agent Skills | 已按 `2026.7.1-2` CLI 核对 |
| Codex | stdio | Agent Skills | 已按当前官方文档核对 |
| Claude Code | stdio | Agent Skills | 已按当前官方文档核对 |
| 其他客户端 | 取决于客户端 | 可选 | 按通用 MCP 契约手工配置 |

“已核对”表示配置格式与上游文档一致，不代表所有未来版本都永久兼容。升级 Agent 后应先执行其版本和 MCP 状态命令。

## 3. 通用调用契约

1. 单链接调用 `easysourceflow_submit_link`，保存返回的 `job_id`。
2. 使用同一 `job_id` 调用 `easysourceflow_get_job`，建议 `wait_seconds=45`。
3. 状态仍为 `queued` 或 `running` 时继续查询，不得改用 Agent 自己的抓取或总结能力。
4. 仅在 `succeeded` 且存在 `result.summary_markdown` 时，将 Markdown 原样交付。
5. 视频使用 `summary_quality="pro"`；普通文章默认 `fast`。
6. 重复链接或附件仍正常提交，并由 EasySourceFlow 缓存决定是否复用。
7. 失败时只转达服务返回的错误和处理建议，不得静默生成替代总结。

`easysourceflow_summarize_link` 仅用于兼容旧调用方处理短网页，不是新 Agent 工作流的默认入口。

## 4. 文档和云文档

- PDF 使用 `easysourceflow_submit_document_file` 提交原始附件；聊天系统注入的文字可能只是预览。
- 已经取得完整正文的 TXT、Markdown、HTML、DOCX 或 EPUB 可调用 `easysourceflow_submit_document`。
- 需要登录的云文档必须由 Agent 已授权的连接器读取完整正文，再把标题、正文和原始 HTTPS `source_url` 提交给 EasySourceFlow。
- 连接器只负责读取，Agent 不得自行总结连接器返回的正文。
- 原始附件路径必须位于 `EASYSOURCEFLOW_DOCUMENT_IMPORT_ROOTS` 允许的目录中。OpenClaw 兼容目录见其专属指南。

飞书读取和消息交付细节见[飞书适配](channels/feishu.md)。

## 5. 通用验收

接入完成后依次验证：

1. 客户端能够列出 `easysourceflow_health` 和 `easysourceflow_submit_link`。
2. 健康检查返回服务可用。
3. 普通文章能进入任务、结果库，并原样返回 Markdown。
4. 视频任务使用 Pro，并显示平台字幕或本地 ASR 来源。
5. PDF 使用原始文件提交；重复发送仍进入 EasySourceFlow。
6. 收到结果后回复“收藏”，只收藏当前结果且不重复发送全文。

完整参数见 [MCP API](MCP_API.md)，Skill 回归场景位于 `skills/easysourceflow/evals/`。
