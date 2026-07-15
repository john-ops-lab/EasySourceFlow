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

控制台可以提交链接和本地文件，下载 B 站/YouTube 音视频，查看平台登录态，配置与测试模型，编辑通用总结提示词，检查 Agent/系统/ASR 状态，取消或重试任务，查看批量报告、结果、收藏和全文搜索。

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
- `preparing_download`: 准备 Web 音视频下载。
- `downloading`: 下载媒体分片。
- `finalizing_download`: 使用 FFmpeg 合并或转换。
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

1. 在 Web“维护 → 账号与授权”点击“扫码登录并自动接入”。
2. 在打开的 Chrome 页面完成扫码；服务会自动检测登录态并显示“已自动接入”。
3. 降低批量处理频率。
4. 自动检测失败或五分钟超时时，使用页面出现的“手动重试”，或配置 Netscape cookies 文件。

不要在日志或聊天中打印 cookies。

### 4.5 YouTube 登录、字幕或 PO Token 问题

处理：

1. 在 Web“维护 → 账号与授权”点击“登录并自动接入”，在打开的 Chrome 页面完成登录。
2. 等待页面显示“已自动接入”，并确认认证来源为“Chrome 实时登录态”；正常情况下无需手工导入 Cookie。
3. 更新 `yt-dlp` 后重试。EasySourceFlow 会区分 `youtube_auth_required`、`youtube_po_token_required` 和 `youtube_rate_limited`。
4. 只有在错误明确要求 PO Token 时，才按照当前 [yt-dlp PO Token Guide](https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide) 配置受支持的 provider 或 `EASYSOURCEFLOW_YOUTUBE_EXTRACTOR_ARGS`。

Cookie 和 PO Token 都属于登录凭据，不要写入 Git、聊天、日志或回归样例。EasySourceFlow 不绕过会员、年龄、地区或其他平台权限。

需要解除授权时，在对应平台卡片点击“退出登录”。该操作会停止自动检测、清除 EasySourceFlow 的登录配置和默认 Cookie 快照，但不会退出 Chrome 中的网站账号；外部手工配置的 Cookie 文件只解除引用，不会删除原文件。

YouTube 会轮换普通浏览器会话 Cookie。若本地 Cookie 文件存在但仍返回 `youtube_auth_required`，重新接入 Chrome；不要把长期保存的 Cookie 文件是否存在当作认证成功的充分条件。

### 4.6 字幕不可用或转写失败

处理：

1. 检查 `yt-dlp`。
2. 检查 `ffmpeg`。
3. 检查 `whisper-cli` 和模型路径。
4. 确认视频时长没有超过 `EASYSOURCEFLOW_MAX_TRANSCRIPTION_SECONDS`。
5. 如果服务由 launchd 托管，重新运行 `scripts/easysourceflow install-launchd` 刷新运行副本和工具路径。

### 4.7 Web 音视频下载失败

1. 确认链接是单个 Bilibili 或 YouTube 视频，不是播放列表。
2. 在“维护 → 账号与授权”重新导入对应平台登录态。
3. 运行 `scripts/easysourceflow sync-runtime` 更新 `yt-dlp[default]` 和 EJS；运行环境升级后再执行 `scripts/easysourceflow install-launchd`。
4. YouTube 需要 Deno 2.3+ 或 Node.js 22+；MP3/M4A 转换和视频合并需要 FFmpeg。

下载文件位于 `EASYSOURCEFLOW_DATA_DIR/media-downloads/<job_id>/`。此功能只在 Web 中提供，不属于 MCP/Agent 能力。系统不处理播放列表、DRM、付费内容或用户无权保存的媒体。

### 4.8 微信浏览器兜底失败

处理：

1. 确认 Playwright Python 包可导入。
2. 确认本机 Google Chrome 存在。
3. 如果 Chrome 不在默认路径，设置 `EASYSOURCEFLOW_CHROME_PATH`。
4. 公开文章仍失败时，建议用户手动提供正文。

服务会复用同一个 Playwright/Chrome 浏览器实例，避免每篇微信文章都冷启动浏览器。

### 4.9 视频平台与 ASR 回归

运行仓库内真实样例：

```bash
scripts/easysourceflow bilibili-regression
scripts/easysourceflow bilibili-regression --force-refresh
scripts/easysourceflow youtube-regression --force-refresh
```

不带 `--force-refresh` 时允许复用有效缓存；带参数时会重新执行抓取、字幕/转写和总结。样例清单位于 `docs/bilibili_regression_samples.json` 和 `docs/youtube_regression_samples.json`。真实平台样例依赖网络、账号、字幕、平台规则和模型额度，不进入普通 CI。

有人工参考文本时评估 ASR：

```bash
scripts/easysourceflow asr-eval reference.txt hypothesis.txt 600
```

输出包含字符错误率、准确率、时间戳单调性和时长覆盖率，不会输出参考文本或转写正文。

### 4.10 完成与失败通知

通过 `.env` 配置通知事件、Webhook 或本地命令，详见配置说明。通知只发送任务标识、状态、标题、错误摘要和输出路径，不发送原文、字幕、API key 或 cookies。通知失败只记录错误类型，不改变任务最终状态。

### 4.11 模型配置检查

Web 控制台会显示当前 provider、Fast/Pro 模型、兼容接口地址和该 provider 的 API Key 是否已配置。模型字段既提供常用预设，也允许输入服务商实际支持的模型 ID。

Web 控制台也会显示当前 ASR 后端、转写时长上限、Whisper 模型路径是否存在，以及文档解析器能力。

模型 provider、Fast/Pro 模型和 API Key 可以在 Web 中保存并测试；Ollama 和默认配置的 LM Studio 使用回环地址，不强制要求 API Key。ASR 配置仍通过 `.env` 或 launchd runtime env 管理。API Key 不会由状态接口返回。

如果当前云端模型调用失败，服务会使用本地抽取式摘要兜底，但结果会明确写出 `local_extractive_fallback` 和失败原因；日志也会记录错误类型。

### 4.12 本地文件输入

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
- 用 YouTube 真实样例验证登录态、平台字幕来源和核心要点时间轴。
- 检查输出目录是否正常写入。

## 9. 当前不处理的问题

- Obsidian 保存失败: 当前没有 Obsidian 写入工具。
- YouTube 平台规则变化: 依赖当前 `yt-dlp`、账号权限和必要时的 PO Token provider，不能保证所有视频长期可用。
- 多用户权限: 当前是本机单用户服务。
