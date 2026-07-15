# 运行手册

## 1. 日常运行

启动服务：

```bash
scripts/easysourceflow start
```

健康检查：

```bash
scripts/easysourceflow health
```

服务默认监听：

```text
http://127.0.0.1:8765
```

Web 控制台：

```text
http://127.0.0.1:8765/
```

控制台可以提交链接、提交本地文件、查看健康状态、查看 B 站 cookies 状态、查看模型/ASR 配置、测试模型连通性、查看最近任务、取消/重试任务、查看批量报告、筛选/全文搜索输出文件并打开输出 Markdown。

常用控制命令：

```bash
scripts/easysourceflow status
scripts/easysourceflow stop
scripts/easysourceflow restart
scripts/easysourceflow logs
scripts/easysourceflow log-status
scripts/easysourceflow rotate-logs
scripts/easysourceflow regression
```

## 2. macOS 开机自启动

安装并启动当前用户的 LaunchAgent：

```bash
scripts/easysourceflow install-launchd
```

查看 LaunchAgent 状态：

```bash
scripts/easysourceflow launchd-status
```

取消开机自启动：

```bash
scripts/easysourceflow uninstall-launchd
```

LaunchAgent 文件位于：

```text
~/Library/LaunchAgents/app.easysourceflow.daemon.plist
```

`launchd` 模式使用独立运行副本：

```text
~/.local/share/easysourceflow/launchd
```

该目录包含同步后的源码、专用虚拟环境、数据库和输出目录。代码更新后重新运行 `scripts/easysourceflow install-launchd`，脚本会刷新运行副本并重启服务。

## 3. 任务状态

常见状态：

- `queued`: 已入队。
- `running`: 正在处理。
- `succeeded`: 已完成。
- `failed`: 失败。
- `canceled`: 用户已取消。
- `interrupted`: 旧任务缺少可恢复输入，服务重启时只能标记失败并提示重试。

新建链接和文档任务会持久化恢复所需输入。服务重启后，处于 `queued` 或 `running` 的任务会自动重新排队；处理过程仍应保持幂等，避免同时运行多个服务实例。

常见阶段：

- `received`: 已收到。
- `extracting`: 抓取网页、字幕或元数据。
- `transcribing`: 转写音频。
- `summarizing`: 调用模型总结。
- `writing_output`: 写入 Markdown 和资源包。
- `done`: 完成。
- `failed`: 失败。

## 4. 常见故障

### 4.1 服务连接失败

现象：

- MCP 返回无法连接 `easysourceflowd`。
- HTTP 请求到 `127.0.0.1:8765` 失败。

处理：

1. 运行 `scripts/easysourceflow status`。
2. 运行 `scripts/easysourceflow health`。
3. 确认 `EASYSOURCEFLOW_BASE_URL` 指向 `http://127.0.0.1:8765`。
4. 如果是 OpenClaw 刚改过 MCP 配置，运行 `openclaw gateway restart`。

### 4.2 模型 API 失败

可能原因：

- `EASYSOURCEFLOW_MODEL_API_KEY` 未配置，或 Web“模型配置”没有保存 API Key。
- 额度不足。
- 网络或 API 服务异常。

处理：

1. 检查 `.env`，不要打印 key。
2. 在 Web“模型选择”中测试当前模型。
3. 运行健康检查。
3. 如果只是模型服务暂时失败，稍后重试。

### 4.3 网页提取失败

可能原因：

- 页面需要登录。
- 页面由 JavaScript 动态渲染。
- 站点阻止抓取。

处理：

- 换公开可访问链接。
- 对微信公众号确认 Playwright 和 Chrome 可用。
- 必要时让用户手动提供正文。

### 4.4 B 站视频需要登录

可能原因：

- 内容需要登录。
- 频率过高触发风控。
- 字幕或元数据接口需要 cookies。

处理：

1. 确认 cookies 文件存在。
2. 在 Web 控制台的“账号与模型”区域确认 cookies 文件路径、大小和修改时间。
3. 降低批量处理频率。
4. 重新导出 cookies 文件。

不要在日志或聊天中打印 cookies。

### 4.5 字幕不可用或转写失败

处理：

1. 检查 `yt-dlp`。
2. 检查 `ffmpeg`。
3. 检查 `whisper-cli` 和模型路径。
4. 确认视频时长没有超过 `EASYSOURCEFLOW_MAX_TRANSCRIPTION_SECONDS`。
5. 如果服务由 launchd 托管，重新运行 `scripts/easysourceflow install-launchd` 刷新运行副本和工具路径。

### 4.6 微信浏览器兜底失败

处理：

1. 确认 Playwright Python 包可导入。
2. 确认本机 Google Chrome 存在。
3. 如果 Chrome 不在默认路径，设置 `EASYSOURCEFLOW_CHROME_PATH`。
4. 公开文章仍失败时，建议用户手动提供正文。

服务会复用同一个 Playwright/Chrome 浏览器实例，避免每篇微信文章都冷启动浏览器。

### 4.9 B 站与 ASR 回归

运行仓库内真实样例：

```bash
scripts/easysourceflow bilibili-regression
scripts/easysourceflow bilibili-regression --force-refresh
```

第一条允许复用有效缓存，第二条会重新执行抓取、字幕/转写和总结。样例清单位于 `docs/bilibili_regression_samples.json`。样例依赖平台内容和网络，失败时先确认链接、cookies、字幕状态和模型额度是否变化。

有人工参考文本时评估 ASR：

```bash
scripts/easysourceflow asr-eval reference.txt hypothesis.txt 600
```

输出包含字符错误率、准确率、时间戳单调性和时长覆盖率，不会输出参考文本或转写正文。

### 4.10 完成与失败通知

通过 `.env` 配置通知事件、Webhook 或本地命令，详见配置说明。通知只发送任务标识、状态、标题、错误摘要和输出路径，不发送原文、字幕、API key 或 cookies。通知失败只记录错误类型，不改变任务最终状态。

### 4.7 模型配置检查

Web 控制台会显示当前 provider、普通模型、强模型、DeepSeek base URL 和 API key 是否已配置。

Web 控制台也会显示当前 ASR 后端、转写时长上限、Whisper 模型路径是否存在，以及文档解析器能力。

模型和 ASR 配置仍通过 `.env` 或 launchd runtime env 管理，Web 页面只做状态展示和连接测试，不写入 API key。

如果 DeepSeek 调用失败，服务会使用本地抽取式摘要兜底，但结果会明确写出 `local_extractive_fallback` 和失败原因；日志也会记录 DeepSeek 的错误类型。

### 4.8 本地文件输入

当前支持：

- `.txt`
- `.md`
- `.markdown`
- `.srt`
- `.vtt`
- `.html`
- `.htm`
- `.docx`
- `.epub`
- `.pdf`

浏览器会读取文件内容并提交给服务。服务不会按用户提供的任意本机路径读取文件。PDF 解析依赖 `pypdf`；运行副本安装脚本会安装它。

## 5. 清理

预览清理：

```bash
scripts/easysourceflow cleanup-preview 14
```

实际删除：

```bash
scripts/easysourceflow cleanup-apply 14
```

清理结果会按类别分组：

- `temp`: 下载音频、临时目录等中间产物。
- `outputs`: 旧输出 Markdown 和资源包日期目录。
- `jobs`: SQLite 旧任务记录；默认不删除，只有显式使用 `--jobs` 时才处理。

MCP 工具 `easysourceflow_cleanup` 默认也是 dry-run。

## 6. 备份

手动备份：

```bash
scripts/easysourceflow backup
```

备份会复制 SQLite 数据库，并把输出目录打包到 `backups/easysourceflow-backup-时间戳`。运行副本模式下，默认位置在：

```text
~/.local/share/easysourceflow/launchd/backups
```

需要备份：

- `.env`。
- `var/easysourceflow.sqlite3`。
- `var/output/`。
- `~/.local/share/easysourceflow/secrets/`，尤其是 cookies 文件。
- `~/.local/share/easysourceflow/models/`，尤其是 Whisper 模型。

备份时不要把 API key 或 cookies 发到聊天里。

每日自动备份和日志轮转：

```bash
scripts/easysourceflow install-maintenance-launchd
scripts/easysourceflow maintenance-status
```

该维护 LaunchAgent 默认每天本机时间 03:15 运行一次 `maintenance-run`，执行 SQLite/输出目录备份，并在日志超过阈值时压缩轮转。取消：

Web“维护”页会显示上一次维护结果。失败时会保留错误类型和错误信息，状态文件位于数据目录下的 `maintenance-status.json`。

```bash
scripts/easysourceflow uninstall-maintenance-launchd
```

只做一次日志轮转检查：

```bash
scripts/easysourceflow rotate-logs
```

本地烟测回归：

```bash
scripts/easysourceflow regression
```

该命令不依赖外网，会临时启动本地文章服务和 EasySourceFlow 服务，验证网页总结、本地文档提交、输出索引和备份。

## 7. 日志

daemon 通过 Python logging 写入 launchd 或脚本配置的日志文件。日志覆盖：

- 服务启动和停止。
- HTTP 请求路径和响应。
- 任务开始、总结、成功、取消和失败。
- 模型 API 失败后的本地兜底。
- SQLite 操作异常。
- MCP 工具调用异常。

## 8. 升级检查清单

升级前：

- 备份 SQLite。
- 记录当前 `.env` 配置项名称。
- 确认没有正在运行的大任务。

升级后：

- 运行测试。
- 运行健康检查。
- 运行 `scripts/easysourceflow backup`。
- 用普通网页验证一次兼容同步接口。
- 用 B 站链接验证 `submit_link` 和同一 `job_id` 的 `get_job` 异步流程。
- 检查输出目录是否正常写入。

## 9. 当前不处理的问题

- Obsidian 保存失败: 当前没有 Obsidian 写入工具。
- YouTube PO Token 或 cookies: 当前不作为短期主线处理。
- 多用户权限: 当前是本机单用户服务。
