# MCP 接口

## 1. 当前原则

- 工具名使用 `easysourceflow_` 前缀。
- Agent 只调用高层工具，不直接调用 `yt-dlp`、`ffmpeg`、Playwright 或文件系统。
- 总结工具默认只输出本地 Markdown，不写入 Obsidian。
- 错误应包含可读原因；底层异常和敏感配置不直接暴露。
- 工具声明包含只读、破坏性、幂等和外部访问提示；这些提示用于 Agent 规划，不代替服务端安全校验。
- MCP 会拒绝未知字段、缺失必填字段和错误参数类型。成功调用同时提供文本结果和结构化服务结果。

当前没有 Obsidian 保存工具。

Web 音视频下载也不属于 MCP 能力。Agent 工具不会创建、列出或交付 `media_download` 任务；下载只能由本机 Web 页面发起。

## 2. 工具列表

### 2.1 `easysourceflow_summarize_link`

兼容旧调用方的短网页同步总结工具。新的 Agent 工作流不应把它作为默认入口。

输入：

```json
{
  "url": "https://example.com/article",
  "instruction": "用中文总结，列出关键要点。"
}
```

行为：

- 普通非视频网页会 POST `/summarize`。
- 创建任务并同步执行。
- 成功时返回任务记录和 `result`。
- `result.output_markdown_path` 指向本地 Markdown 文件。
- MCP 文本结果会把 `result.summary_markdown` 标记为 EasySourceFlow 最终 Markdown；Agent 应直接转交，不应默认二次总结或重写。
- B 站和 YouTube 链接会返回 `video_requires_async`，不会在同步工具内偷偷创建异步任务。

仅用于需要兼容同步行为的短网页。Agent 处理所有新链接时应使用异步工具。

### 2.2 `easysourceflow_submit_link`

提交一个链接进行可恢复的后台处理。这是 Agent 总结任意链接时的默认入口。

输入：

```json
{
  "url": "https://www.bilibili.com/video/BV...",
  "instruction": "总结成结构化笔记。",
  "summary_quality": "pro",
  "force_refresh": false
}
```

行为：

- POST `/jobs`。
- 立即返回 `job_id`。
- 保存返回的 `job_id`，后续用 `easysourceflow_get_job` 独立查询。
- `queued` 或 `running` 不是失败，不能因此改用网页抓取或自行总结。
- `force_refresh=true` 会跳过已有缓存；仅在用户明确要求重新抓取、重新转写或重新总结时使用。

典型输出：

```json
{
  "job_id": "job_...",
  "status": "queued",
  "stage": "received",
  "progress": 0
}
```

### 2.3 `easysourceflow_get_job`

查询单个任务。

输入：

```json
{
  "job_id": "job_...",
  "wait_seconds": 45
}
```

`wait_seconds` 可取 0 到 45，默认 0。传 45 时，工具会在本次调用中等待任务状态变化；到时仍未完成会返回当前状态，Agent 应使用同一 `job_id` 再次调用。

成功任务会包含：

```json
{
  "job_id": "job_...",
  "status": "succeeded",
  "stage": "done",
  "progress": 1.0,
  "title": "Example",
  "result": {
    "summary_markdown": "...",
    "output_markdown_path": "~/.local/share/easysourceflow/output/..."
  }
}
```

失败任务会包含 `error_code` 和 `error_message`。

只有 `status=succeeded` 且存在 `result.summary_markdown` 才表示总结完成。成功任务的 MCP 文本结果会把该字段标记为最终 Markdown，Agent 默认应直接返回并保留 `output_markdown_path`，除非用户明确要求“再压缩/改写”。

### 2.4 `easysourceflow_favorite_result`

收藏一份已经生成的总结及其原材料资源包。

优先传入当前结果的标识：

```json
{
  "job_id": "job_..."
}
```

也可以传入 `output_markdown_path` 或 `relative_path`。三个参数都省略时，服务会收藏最近一份输出。已经收藏的结果不会重复复制。

### 2.5 `easysourceflow_submit_batch`

提交多个链接进行后台处理。

输入：

```json
{
  "urls": [
    "https://example.com/article",
    "https://www.bilibili.com/video/BV..."
  ],
  "instruction": "用中文总结。"
}
```

行为：

- POST `/batches`。
- 每个 URL 独立创建任务。
- 返回 `batch_id` 和任务列表。

### 2.6 `easysourceflow_cancel_job`

取消一个等待或运行中的任务。

输入：

```json
{
  "job_id": "job_..."
}
```

行为：

- POST `/jobs/{job_id}/cancel`。
- 已完成、已失败或已取消任务会原样返回。
- 运行中任务如果已经进入底层下载/转写子进程，子进程可能会在后台自然结束；任务记录会保持 `canceled`，不会被后续成功结果覆盖。

### 2.7 `easysourceflow_retry_job`

重试已有任务，可覆盖 `instruction` 和 `summary_quality`。默认 `force_refresh=true`，避免重复命中导致上次结果不符合预期的缓存；传 `false` 才允许复用缓存。

### 2.8 `easysourceflow_get_batch`

查询批量任务状态。

输入：

```json
{
  "batch_id": "batch_..."
}
```

输出包含：

- `status_counts`
- `items`
- `summary.succeeded`
- `summary.failed`
- `summary.running`

### 2.9 `easysourceflow_submit_document_file`

提交用户刚上传的原始附件，尤其适用于聊天系统只提供部分 PDF 文字预览的情况。

```json
{
  "file_path": "<AGENT_UPLOAD_DIR>/document.pdf",
  "title": "document.pdf",
  "force_refresh": false
}
```

MCP 适配器默认只允许 OpenClaw 标准上传目录 `<OPENCLAW_STATE_DIR>/media/inbound`。其他 Agent 需在自己的 MCP 进程环境中设置 `EASYSOURCEFLOW_DOCUMENT_IMPORT_ROOTS`，多个目录使用操作系统路径分隔符连接。文件上限默认 50 MiB，可用 `EASYSOURCEFLOW_DOCUMENT_IMPORT_MAX_BYTES` 调整，最高 200 MiB。路径不在白名单、文件消失、类型不支持或超过上限时，不会读取文件。

### 2.10 `easysourceflow_list_recent_jobs`

列出最近任务。

输入：

```json
{
  "limit": 20,
  "status": "succeeded"
}
```

`status` 可省略。`limit` 在服务端限制为 1 到 100。

### 2.11 `easysourceflow_health_check`

查询运行健康状态。

行为：

- GET `/health`。
- 检查输出目录、当前模型 API、yt-dlp、ffmpeg、whisper、B 站/YouTube cookies、微信浏览器兜底等。

### 2.12 `easysourceflow_cleanup`

预览或删除旧输出和临时文件。

输入：

```json
{
  "days": 14,
  "dry_run": true
}
```

默认 `dry_run=true`。只有明确传入 `dry_run=false` 时才会删除。

### 2.13 `easysourceflow_backup`

备份本机 SQLite 数据库和输出目录。

输入：

```json
{}
```

行为：

- POST `/backup`。
- 返回备份目录、清单文件和 `latest` 指针。
- 不返回 API key 或 cookies 内容。

## 3. HTTP 对应关系

| MCP 工具 | HTTP |
| --- | --- |
| `easysourceflow_summarize_link` | `POST /summarize` |
| `easysourceflow_submit_link` | `POST /jobs` |
| `easysourceflow_get_job` | `GET /jobs/{job_id}` |
| `easysourceflow_favorite_result` | `POST /favorites` |
| `easysourceflow_retry_job` | `POST /jobs/{job_id}/retry` |
| `easysourceflow_cancel_job` | `POST /jobs/{job_id}/cancel` |
| `easysourceflow_submit_document` | `POST /documents` |
| `easysourceflow_submit_document_file` | 读取受限上传目录后 `POST /documents` |
| `easysourceflow_submit_batch` | `POST /batches` |
| `easysourceflow_get_batch` | `GET /batches/{batch_id}` |
| `easysourceflow_list_recent_jobs` | `GET /jobs` |
| `easysourceflow_search_outputs` | `GET /search` |
| `easysourceflow_bilibili_cookie_status` | `GET /cookies/bilibili` |
| `easysourceflow_model_status` | `GET /model` |
| `easysourceflow_health_check` | `GET /health` |
| `easysourceflow_cleanup` | `POST /cleanup` |
| `easysourceflow_backup` | `POST /backup` |

Web 控制台相关 HTTP endpoint：

| Endpoint | 说明 |
| --- | --- |
| `GET /` | 本机 Web 控制台 |
| `GET /outputs` | 输出 Markdown 文件列表，包含来源和日期统计 |
| `GET /outputs/{relative_path}` | 浏览器查看某个输出 Markdown |
| `GET /search` | 全文搜索输出 Markdown |
| `GET /batches` | 最近批量任务列表 |
| `GET /queue` | 队列状态和状态计数 |
| `GET /cookies/bilibili` | B 站 cookies 文件状态，不返回 cookies 内容 |
| `GET /model` | 模型配置状态，不返回 API key |
| `POST /model` | 保存 provider、模型名、接口地址和 API Key |
| `POST /model/test` | 测试当前模型 provider |
| `GET /maintenance/status` | 上一次维护任务结果 |
| `POST /documents` | 提交本地文本、HTML、DOCX、EPUB 或 PDF 内容 |
| `POST /jobs/{job_id}/cancel` | 取消等待或运行中的任务 |
| `POST /jobs/{job_id}/retry` | 重试旧任务 |
| `POST /backup` | 备份 SQLite 和输出目录 |

任务失败时，job 记录会尽量包含 `error_next_steps`，用于告诉 Agent 或 Web 控制台下一步怎么处理。

## 4. Agent 调用建议

推荐同时安装仓库中的官方 Skill。MCP 负责工具能力，Skill 负责视频默认 Pro、最终 Markdown 原样交付、收藏最近结果等对话行为。安装方式见 [Agent 接入指南](AGENT_INTEGRATION.md)。

任意单个链接：

1. 调用 `easysourceflow_submit_link`。
2. 保存 `job_id`，调用 `easysourceflow_get_job`，建议传 `wait_seconds=45`。
3. 如果仍是 `queued` 或 `running`，使用同一 `job_id` 继续查询，不得改用其他抓取或总结工具。
4. 仅在 `succeeded` 且存在 `summary_markdown` 时，把原始 Markdown、输出路径和资源包路径交付给用户。
5. 如果是 `failed` 或 `canceled`，只转达 EasySourceFlow 的错误和建议，不生成替代总结。

多个链接：

1. 调用 `easysourceflow_submit_batch`。
2. 轮询 `easysourceflow_get_batch`。
3. 对失败项单独解释原因。

## 5. 输入约束

- URL 必须是 HTTP/HTTPS。
- 默认拒绝 localhost、私有 IP 和 link-local 地址。
- 本地文件输入只接收调用方提交的文件内容或文本内容，不接收任意本机路径读取请求。
- Web 上传支持 txt、md、srt、vtt、html、docx、epub、pdf；PDF 解析依赖运行环境中的 `pypdf`。
- `instruction` 应保持简短明确。
- `cleanup` 默认 dry-run。
