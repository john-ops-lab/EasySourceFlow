# Configuration

EasySourceFlow reads configuration from environment variables and an optional `.env` file in the repository root. Set `EASYSOURCEFLOW_CONFIG_FILE` to use another file.

Copy the template before running the service:

```bash
cp .env.example .env
```

Never commit `.env`, API keys, cookies, database files, logs, generated outputs, or downloaded media.

## Core Runtime

| Variable | Default | Description |
| --- | --- | --- |
| `EASYSOURCEFLOW_HOST` | `127.0.0.1` | HTTP bind host. Keep localhost unless you understand the security impact. |
| `EASYSOURCEFLOW_PORT` | `8765` | HTTP port. |
| `EASYSOURCEFLOW_DATA_DIR` | `~/.local/share/easysourceflow` | SQLite database, secrets, models, and temporary runtime data. |
| `EASYSOURCEFLOW_DATABASE` | `$EASYSOURCEFLOW_DATA_DIR/easysourceflow.sqlite3` | SQLite database path. |
| `EASYSOURCEFLOW_OUTPUT_DIR` | `$EASYSOURCEFLOW_DATA_DIR/output` | Markdown output and resource packages. |
| `EASYSOURCEFLOW_ALLOW_LOCAL_URLS` | `false` | Allow localhost/private URL fetching. Keep disabled for normal use. |
| `EASYSOURCEFLOW_TRUST_FAKE_IP` | `false` | Trust configured fake-IP ranges for domain resolution. Enable only when a local proxy owns those ranges. |
| `EASYSOURCEFLOW_FAKE_IP_CIDRS` | `198.18.0.0/15` | Comma-separated non-global CIDRs trusted when fake-IP mode is enabled. |
| `EASYSOURCEFLOW_REQUEST_TIMEOUT` | `20` | Network request timeout in seconds. |
| `EASYSOURCEFLOW_MAX_CONTENT_CHARS` | `120000` | Maximum extracted content sent to the summarizer. |
| `EASYSOURCEFLOW_CACHE_TTL_SECONDS` | `604800` | Successful-link cache lifetime. Set `0` to disable cache reads. |
| `EASYSOURCEFLOW_PROJECT_ROOT` | package root | Project root used to locate local MCP tooling. The launchd installer sets it automatically. |

## Fake-IP 代理环境

Surge、Clash 和 Mihomo 等代理的 fake-ip 模式可能把公网域名解析到 `198.18.0.0/15`。严格模式会把这类非公网结果作为 SSRF 风险拒绝。可在 Web 的“维护 → 网络与安全”中开启 trusted 模式，也可以设置：

```bash
EASYSOURCEFLOW_TRUST_FAKE_IP=true
EASYSOURCEFLOW_FAKE_IP_CIDRS=198.18.0.0/15
```

其他 fake-ip 网段必须明确添加。该模式只豁免“域名解析到可信网段”的情况；直接提交保留 IP、loopback、link-local 或 multicast 地址仍会被拒绝。`EASYSOURCEFLOW_ALLOW_LOCAL_URLS=true` 会跳过全部本地地址校验，风险更高，不应作为 fake-ip 的常规解决方案。

## Model Provider

| Variable | Default | Description |
| --- | --- | --- |
| `EASYSOURCEFLOW_MODEL_PROVIDER` | `local` | `local` or `openai_compatible`. |
| `EASYSOURCEFLOW_MODEL` | `deepseek-v4-flash` | Default model for fast summaries. |
| `EASYSOURCEFLOW_STRONG_MODEL` | `deepseek-v4-pro` | Strong model for video/pro summaries. |
| `EASYSOURCEFLOW_MODEL_BASE_URL` | `https://api.deepseek.com` | OpenAI-compatible API base URL. |
| `EASYSOURCEFLOW_MODEL_API_KEY` | empty | API key. Required for cloud model summaries; optional for loopback Ollama/LM Studio endpoints. |
| `EASYSOURCEFLOW_MODEL_API_KEY_<SERVICE_ID>` | empty | Web-managed credential for one provider, such as `..._DEEPSEEK` or `..._OPENAI`. Values are never returned by the API. |
| `EASYSOURCEFLOW_SUMMARY_PROMPT_FILE` | `$DATA_DIR/config/summary-prompt.txt` | Multiline hard rules and Markdown template shared by every configured cloud model. |
| `EASYSOURCEFLOW_SUMMARY_PROMPT` | built-in prompt | Optional one-line fallback when the prompt file does not exist. |
| `EASYSOURCEFLOW_SUMMARY_SYSTEM_PROMPT` | empty | Deprecated compatibility alias for `EASYSOURCEFLOW_SUMMARY_PROMPT`. |
| `DEEPSEEK_BASE_URL` / `DEEPSEEK_API_KEY` | empty | Backward-compatible aliases. Prefer `EASYSOURCEFLOW_MODEL_*`. |

The Web console stores credentials separately for each preset provider. The generic `EASYSOURCEFLOW_MODEL_API_KEY` value always represents the active provider, so switching providers cannot silently reuse another provider's key. Preset model IDs are suggestions: the Fast and Pro fields also accept a model ID supported by the selected service.

The Web prompt is model-independent: every configured cloud or local generative model receives the same rules and Markdown template. EasySourceFlow appends source metadata, source-specific requirements, and content at runtime. The local extractive fallback does not call a model and therefore does not use this prompt. Changing the prompt invalidates the summary cache for new jobs.

## Agent Integration

| Variable | Default | Description |
| --- | --- | --- |
| `EASYSOURCEFLOW_AGENT_WORKSPACE` | empty | Optional local Agent workspace used by the Web status page. Store real paths only in the ignored `.env` file. |

The Web console reports component readiness separately from actual MCP activity. “Recently connected” means the service received an MCP request within the last 10 minutes; it does not claim that an Agent process is permanently online.

## Video, Cookies, and ASR

| Variable | Default | Description |
| --- | --- | --- |
| `EASYSOURCEFLOW_YTDLP_PATH` | auto-detect | Optional path to `yt-dlp`. |
| `EASYSOURCEFLOW_BILIBILI_COOKIES_FILE` | empty | Netscape cookies file for Bilibili. If empty, the service uses `$DATA_DIR/secrets/bilibili-cookies.txt` when present. |
| `EASYSOURCEFLOW_YOUTUBE_COOKIES_FILE` | auto-detect | Netscape cookies file for YouTube. If empty, the service uses `$DATA_DIR/secrets/youtube-cookies.txt` when present. |
| `EASYSOURCEFLOW_YOUTUBE_BROWSER_COOKIE_SOURCE` | empty | Live yt-dlp browser source such as `chrome:Default`. Set automatically by Web import and preferred over the cookie file. |
| `EASYSOURCEFLOW_YOUTUBE_EXTRACTOR_ARGS` | empty | Optional value passed to yt-dlp `--extractor-args` for current YouTube client or PO Token requirements. |
| `EASYSOURCEFLOW_FFMPEG_PATH` | `ffmpeg` | Path or command name for ffmpeg. |
| `EASYSOURCEFLOW_WHISPER_CLI_PATH` | `whisper-cli` | Path or command name for whisper.cpp CLI. |
| `EASYSOURCEFLOW_WHISPER_MODEL_PATH` | `$DATA_DIR/models/ggml-base.bin` | whisper.cpp model path. |
| `EASYSOURCEFLOW_TRANSCRIPTION_BACKEND` | `whisper_cpp` | `whisper_cpp`, `mlx_whisper`, or `faster_whisper`. |
| `EASYSOURCEFLOW_MLX_WHISPER_PATH` | `mlx_whisper` | Optional MLX Whisper command. |
| `EASYSOURCEFLOW_FASTER_WHISPER_PATH` | `faster-whisper` | Optional faster-whisper command. |
| `EASYSOURCEFLOW_MAX_TRANSCRIPTION_SECONDS` | `7200` | Maximum video duration for local ASR fallback. |

The Web maintenance page can import Bilibili login state and connect a local Chrome profile for YouTube. Bilibili uses a filtered `0600` cookie file. YouTube tasks prefer the configured live Chrome source because YouTube rotates cookies in normal browser sessions; the filtered file is only a local status snapshot and compatibility fallback. The HTTP response and logs never include cookie values.

YouTube selection order is: creator-provided Chinese subtitles, other creator-provided subtitles, original-language automatic captions, other automatic captions, then local ASR. English captions are accepted as source material; the configured summary model still produces Chinese Markdown. PO Token requirements vary by YouTube client and yt-dlp version, so EasySourceFlow does not embed a token generator. Follow the current [yt-dlp PO Token Guide](https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide) when the returned status is `youtube_po_token_required`.

The Web-only media downloader requires `yt-dlp[default]`, FFmpeg, and a JavaScript runtime for current YouTube challenges. Deno 2.3+ is preferred; Node 22+ is the fallback. Downloads are limited to one Bilibili or YouTube video per task and are stored under `$EASYSOURCEFLOW_DATA_DIR/media-downloads/`. No download tool is exposed through MCP.

## Browser Fallback

| Variable | Default | Description |
| --- | --- | --- |
| `EASYSOURCEFLOW_CHROME_PATH` | platform default | Optional Chrome executable path for WeChat/browser fallback. |
| `EASYSOURCEFLOW_WECHAT_MARKDOWN_COMMAND` | empty | Optional external command for WeChat article extraction. Use `{url}` as the URL placeholder. |

## macOS LaunchAgent

| Variable | Default | Description |
| --- | --- | --- |
| `EASYSOURCEFLOW_LAUNCHD_LABEL` | `app.easysourceflow.daemon` | LaunchAgent label. Change it if packaging or running multiple copies. |
| `EASYSOURCEFLOW_MAINTENANCE_LABEL` | `app.easysourceflow.maintenance` | Daily maintenance LaunchAgent label. |
| `EASYSOURCEFLOW_LAUNCHD_RUNTIME_DIR` | `~/.local/share/easysourceflow/launchd` | Runtime copy used by launchd. |

Run `scripts/easysourceflow health` after changing configuration.

## Notifications

Notifications are disabled until `EASYSOURCEFLOW_NOTIFICATION_EVENTS` is configured. Supported events are `job.succeeded`, `job.failed`, `job.canceled`, `maintenance.succeeded`, and `maintenance.failed`.

| Variable | Default | Description |
| --- | --- | --- |
| `EASYSOURCEFLOW_NOTIFICATION_EVENTS` | empty | Comma-separated events to deliver. |
| `EASYSOURCEFLOW_NOTIFICATION_WEBHOOK_URL` | empty | Optional HTTP/HTTPS endpoint receiving minimal JSON. |
| `EASYSOURCEFLOW_NOTIFICATION_WEBHOOK_TOKEN` | empty | Optional bearer token for the webhook. |
| `EASYSOURCEFLOW_NOTIFICATION_COMMAND` | empty | Optional local command. It is executed without a shell and receives JSON on stdin. |

Notification payloads contain task status, title, error, and output paths only. They never contain source bodies, transcripts, cookies, or model credentials.
