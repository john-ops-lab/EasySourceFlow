# 技术设计

## 1. 当前技术栈

- 语言: Python。
- HTTP 服务: `http.server.ThreadingHTTPServer`。
- MCP: 自实现 stdio JSON-RPC 适配器。
- 任务存储: SQLite。
- 网页提取: 标准库 HTTP、HTML 解析和元数据提取。
- 微信公众号兜底: Playwright Python 包和本机 Google Chrome。
- 视频提取: `yt-dlp`。
- 音频处理: `ffmpeg`。
- 转写: `whisper_cpp`，并保留 `mlx_whisper`、`faster_whisper` 配置。
- 总结: OpenAI-compatible Chat Completions API；Web 预置 DeepSeek、OpenAI、Qwen、Kimi、智谱和 OpenRouter。
- 输出: 本地 Markdown 文件和视频资源包。
- Web 控制台: 内置 HTML/CSS/JavaScript，挂载在 `GET /`。

当前没有 Obsidian 写入模块。

## 2. 目录结构

```text
.
├── README.md
├── docs/
├── pyproject.toml
├── src/
│   ├── easysourceflow_mcp/
│   │   └── server.py
│   └── easysourceflow_core/
│       ├── cleanup.py
│       ├── config.py
│       ├── daemon.py
│       ├── digest.py
│       ├── errors.py
│       ├── health.py
│       ├── http_api.py
│       ├── models.py
│       ├── output.py
│       ├── service.py
│       ├── store.py
│       ├── url_utils.py
│       ├── web_ui.py
│       └── extractors/
│           ├── video.py
│           ├── web.py
│           └── wechat.py
├── tests/
└── var/
    ├── downloads/
    ├── output/
    └── easysourceflow.sqlite3
```

## 3. 配置

配置从 `.env` 和环境变量读取。`.env` 默认位于项目根目录，也可以用 `EASYSOURCEFLOW_CONFIG_FILE` 指向其他文件。

主要配置：

```env
EASYSOURCEFLOW_HOST=127.0.0.1
EASYSOURCEFLOW_PORT=8765
EASYSOURCEFLOW_DATA_DIR=~/.local/share/easysourceflow
EASYSOURCEFLOW_OUTPUT_DIR=~/.local/share/easysourceflow/output
EASYSOURCEFLOW_BILIBILI_COOKIES_FILE=~/.local/share/easysourceflow/secrets/bilibili-cookies.txt
EASYSOURCEFLOW_YOUTUBE_COOKIES_FILE=~/.local/share/easysourceflow/secrets/youtube-cookies.txt
EASYSOURCEFLOW_FFMPEG_PATH=ffmpeg
EASYSOURCEFLOW_WHISPER_CLI_PATH=whisper-cli
EASYSOURCEFLOW_WHISPER_MODEL_PATH=~/.local/share/easysourceflow/models/ggml-base.bin
EASYSOURCEFLOW_TRANSCRIPTION_BACKEND=whisper_cpp
EASYSOURCEFLOW_MODEL_PROVIDER=openai_compatible
EASYSOURCEFLOW_MODEL=deepseek-v4-flash
EASYSOURCEFLOW_STRONG_MODEL=deepseek-v4-pro
EASYSOURCEFLOW_MODEL_BASE_URL=https://api.deepseek.com
EASYSOURCEFLOW_MODEL_API_KEY=...
```

`.env` 不应打印、提交或复制到交接文档中。

## 4. URL 规范化

规范化步骤：

1. 只接受 `http` 和 `https`。
2. 默认拒绝 localhost、私有 IP 和 link-local 地址。
3. 去除常见追踪参数。
4. 识别来源类型。
5. 使用规范化 URL 和用户指令作为缓存键。

## 5. 提取模型

所有提取器返回 `SourceDocument`：

```python
@dataclass
class SourceDocument:
    source_url: str
    canonical_url: str
    source_type: str
    title: str
    author: str | None
    published_at: str | None
    language: str | None
    content_text: str
    content_markdown: str
    metadata: dict
    extraction_method: str
```

## 6. 普通网页提取策略

普通网页提取器负责：

- 下载公开 HTML。
- 提取标题、作者、发布时间、OpenGraph、JSON-LD 等元数据。
- 过滤明显噪声。
- 生成正文文本和 Markdown。

失败时返回 `extraction_failed`。

## 7. 微信公众号提取策略

微信公众号走独立提取器。

优先级：

1. 直接读取公开 HTML。
2. 提取 `#js_content`、标题、公众号名、发布时间。
3. 收集 `data-src`、`src`、`msg_title`、`nickname`、`ct` 等常见字段。
4. 使用外部 Markdown 命令兜底。
5. 使用 Playwright / Chrome 兜底。

限制：

- 不绕过登录或风控。
- 不批量高频抓取。
- 失败时返回可读错误。

## 8. 视频提取策略

### 8.1 默认流程

```text
yt-dlp metadata
  -> platform subtitles
  -> transcript normalization
  -> configured model summary
  -> Markdown and resource package
```

### 8.2 B 站字幕

B 站优先使用平台字幕接口，不只依赖 `yt-dlp` 的字幕字段。cookies 文件用于提高稳定性。

### 8.3 转写兜底

当字幕不可用，且视频时长不超过 `EASYSOURCEFLOW_MAX_TRANSCRIPTION_SECONDS`：

```text
yt-dlp audio
  -> ffmpeg
  -> whisper backend
  -> transcript
  -> summary
```

默认不下载完整视频。

### 8.4 YouTube

YouTube 使用独立字幕选择流程：优先人工中文字幕，其次其他人工字幕；没有人工字幕时优先原语言自动字幕，再尝试其他自动字幕。只有平台字幕均不可用时才下载音频进入本地 ASR。

Web 可以从本机 Chrome 导入登录态。导入过程只保留 `youtube.com` 域 Cookie，使用私有临时文件和原子替换写入数据目录。PO Token 不内置生成器；当 yt-dlp 明确要求时，通过当前受支持的 provider 或 `EASYSOURCEFLOW_YOUTUBE_EXTRACTOR_ARGS` 配置。

## 9. 总结策略

总结输入包括：

- 用户指令。
- 来源类型。
- 标题、作者、发布时间。
- 正文、字幕或转写文本。
- 提取质量提示。

输出包括：

- 标题。
- 摘要。
- 关键要点。
- 重要细节。
- 用户指令要求的专门部分。
- 标签建议。

当前 `save_recommendation` 仅作为总结内容的一部分，不触发 Obsidian 写入。

## 10. 输出策略

普通 Markdown 输出：

```text
EASYSOURCEFLOW_OUTPUT_DIR/YYYY-MM-DD/<source_type>/<time-title>.md
```

每个来源目录维护：

```text
latest.md
```

视频资源包根据可用素材写入：

- `summary.md`
- `metadata.json`
- `source_info.json`
- `raw_metadata.json`
- `subtitle.vtt`
- `transcript.txt`
- `transcript_with_timestamps.txt`

## 11. 任务和缓存

SQLite 表：

- `jobs`
- `result_cache`
- `batches`

任务字段包括：

- `job_id`
- `url`
- `canonical_url`
- `instruction`
- `status`
- `stage`
- `progress`
- `title`
- `result_json`
- `error_code`
- `error_message`
- `created_at`
- `updated_at`

## 12. 错误模型

内部错误使用 `EasySourceFlowError`，包含：

- `code`
- `message`
- `next_steps`

当前持久化到任务表的是 `error_code` 和 `error_message`。

## 13. 日志和敏感信息

不得记录：

- API key。
- cookies。
- 完整正文。
- 完整字幕。
- `.env` 内容。

可以记录：

- job id。
- 来源类型。
- 阶段。
- 错误码。
- 依赖检查结果。

## 14. 当前实现顺序状态

已完成：

1. 配置、数据模型、SQLite store。
2. 本地 HTTP API。
3. MCP 适配器。
4. 普通网页提取。
5. 微信公众号提取和浏览器兜底。
6. 模型 API 总结。
7. B 站字幕和转写兜底。
8. YouTube 登录态、字幕优先级和转写兜底。
9. Markdown 输出和视频资源包。
10. 批量链接。
11. 清理工具。
12. 健康检查。

后续：

1. 本地菜单栏入口。
2. 持续维护真实 B 站回归样例和 ASR 基准。
3. B 站多 P 视频支持。
4. 任务恢复后的严格输出幂等。
5. Obsidian 入库。
6. 持续跟进 YouTube 客户端和 PO Token 规则变化。
