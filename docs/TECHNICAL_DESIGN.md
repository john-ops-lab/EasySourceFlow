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
- 总结: OpenAI-compatible Chat Completions 和 Responses API；Web 预置常见国内外云端服务商及 Ollama、LM Studio 本地服务。
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
│       ├── media_download.py
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
EASYSOURCEFLOW_MODEL=deepseek-chat
EASYSOURCEFLOW_STRONG_MODEL=deepseek-reasoner
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

B 站先由视图接口解析精确的 `bvid`、分 P 和 `cid`，再使用 `x/player/wbi/v2` 获取字幕；不回退到旧的 `x/player/v2`。候选按人工中文、AI 中文、其他人工字幕、其他自动字幕排序。cookies 文件用于提高稳定性。

对于 `b23.tv` 等不含 BVID 的短链接，`yt-dlp` 完成重定向和元数据提取后，服务只接受其返回的 B站域名页面地址，从中恢复 BVID 和分 P，并生成不含分享会话参数的规范地址。用户提交的短链接仍保存在 `source_url`，字幕接口和结果跳转使用规范地址；已取得可信平台字幕时不得启动本地 ASR。

字幕进入总结前必须通过时间结构校验：时间段有效、起点单调、末时间不超过视频时长容差，长视频不能严重缺失尾部。标题和标签的词语重合不能证明字幕身份，因此不作为接受条件。若平台字幕均不可信，则进入本地 ASR；ASR 也不可用时任务以 `transcript_unavailable` 失败，禁止仅总结视频标题和简介。

资源包中的 `subtitle_provenance` 记录 BVID、CID、分 P、字幕 ID、视频时长、字幕末时间、时长比和内容哈希，不保存带认证参数的字幕 URL。

### 8.3 转写兜底

当字幕不可用，且视频时长不超过 `EASYSOURCEFLOW_MAX_TRANSCRIPTION_SECONDS`：

```text
yt-dlp audio
  -> ffmpeg
  -> whisper backend
  -> transcript
  -> summary
```

总结和 ASR 流程默认不保存完整视频；完整媒体只由 Web 下载页显式触发。

### 8.4 Web 专用音视频下载

Web 的 `/downloads` 接口创建 `request_kind=media_download` 的持久化任务。只接受 Bilibili/YouTube 单视频链接和固定白名单选项：视频为 1080p、720p、最高画质；音频为 MP3、M4A、原始音频。

子进程始终使用参数数组，并固定启用 `--no-playlist`、`--no-overwrites`、受控输出模板和专用任务目录。完成后校验文件仍位于 `EASYSOURCEFLOW_DATA_DIR/media-downloads/<job_id>/`。YouTube 使用 `yt-dlp[default]` 的 EJS 包及 Deno/Node 挑战求解；该接口不进入 MCP 工具表。

### 8.5 YouTube

YouTube 使用独立字幕选择流程：优先人工中文字幕，其次其他人工字幕；没有人工字幕时优先原语言自动字幕，再尝试其他自动字幕。只有平台字幕均不可用时才下载音频进入本地 ASR。

Web 可以接入本机 Chrome 登录态。接入时生成只含 `youtube.com` 域的私有状态快照，但任务执行优先使用 `EASYSOURCEFLOW_YOUTUBE_BROWSER_COOKIE_SOURCE` 直接读取当前 Chrome 配置档，避免普通会话 Cookie 轮换后继续复用失效文件。PO Token 不内置生成器；当 yt-dlp 明确要求时，通过当前受支持的 provider 或 `EASYSOURCEFLOW_YOUTUBE_EXTRACTOR_ARGS` 配置。

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
