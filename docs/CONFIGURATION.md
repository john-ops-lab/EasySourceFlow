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
| `EASYSOURCEFLOW_REQUEST_TIMEOUT` | `20` | Network request timeout in seconds. |
| `EASYSOURCEFLOW_MAX_CONTENT_CHARS` | `120000` | Maximum extracted content sent to the summarizer. |
| `EASYSOURCEFLOW_CACHE_TTL_SECONDS` | `604800` | Successful-link cache lifetime. Set `0` to disable cache reads. |
| `EASYSOURCEFLOW_PROJECT_ROOT` | package root | Project root used to locate local MCP tooling. The launchd installer sets it automatically. |

## Model Provider

| Variable | Default | Description |
| --- | --- | --- |
| `EASYSOURCEFLOW_MODEL_PROVIDER` | `local` | `local` or `openai_compatible`. |
| `EASYSOURCEFLOW_MODEL` | `deepseek-v4-flash` | Default model for fast summaries. |
| `EASYSOURCEFLOW_STRONG_MODEL` | `deepseek-v4-pro` | Strong model for video/pro summaries. |
| `EASYSOURCEFLOW_MODEL_BASE_URL` | `https://api.deepseek.com` | OpenAI-compatible API base URL. |
| `EASYSOURCEFLOW_MODEL_API_KEY` | empty | API key. Required for cloud model summaries. |
| `EASYSOURCEFLOW_MODEL_API_KEY_<SERVICE_ID>` | empty | Web-managed credential for one provider, such as `..._DEEPSEEK` or `..._OPENAI`. Values are never returned by the API. |
| `EASYSOURCEFLOW_SUMMARY_PROMPT_FILE` | `$DATA_DIR/config/summary-prompt.txt` | Multiline hard rules and Markdown template shared by every configured cloud model. |
| `EASYSOURCEFLOW_SUMMARY_PROMPT` | built-in prompt | Optional one-line fallback when the prompt file does not exist. |
| `EASYSOURCEFLOW_SUMMARY_SYSTEM_PROMPT` | empty | Deprecated compatibility alias for `EASYSOURCEFLOW_SUMMARY_PROMPT`. |
| `DEEPSEEK_BASE_URL` / `DEEPSEEK_API_KEY` | empty | Backward-compatible aliases. Prefer `EASYSOURCEFLOW_MODEL_*`. |

The Web console stores credentials separately for each preset provider. The generic `EASYSOURCEFLOW_MODEL_API_KEY` value always represents the active provider, so switching providers cannot silently reuse another provider's key.

The Web prompt is model-independent: DeepSeek, OpenAI, Qwen, Kimi, GLM, and other OpenAI-compatible services all receive the same configured rules and Markdown template. EasySourceFlow appends source metadata, source-specific requirements, and content at runtime. The local extractive fallback does not call a model and therefore does not use this prompt. Changing the prompt invalidates the summary cache for new jobs.

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
| `EASYSOURCEFLOW_YOUTUBE_EXTRACTOR_ARGS` | empty | Optional value passed to yt-dlp `--extractor-args` for current YouTube client or PO Token requirements. |
| `EASYSOURCEFLOW_FFMPEG_PATH` | `ffmpeg` | Path or command name for ffmpeg. |
| `EASYSOURCEFLOW_WHISPER_CLI_PATH` | `whisper-cli` | Path or command name for whisper.cpp CLI. |
| `EASYSOURCEFLOW_WHISPER_MODEL_PATH` | `$DATA_DIR/models/ggml-base.bin` | whisper.cpp model path. |
| `EASYSOURCEFLOW_TRANSCRIPTION_BACKEND` | `whisper_cpp` | `whisper_cpp`, `mlx_whisper`, or `faster_whisper`. |
| `EASYSOURCEFLOW_MLX_WHISPER_PATH` | `mlx_whisper` | Optional MLX Whisper command. |
| `EASYSOURCEFLOW_FASTER_WHISPER_PATH` | `faster-whisper` | Optional faster-whisper command. |
| `EASYSOURCEFLOW_MAX_TRANSCRIPTION_SECONDS` | `7200` | Maximum video duration for local ASR fallback. |

The Web maintenance page can import Bilibili or YouTube login state from the local Chrome profile. Import first exports to a private temporary file, keeps only cookies belonging to the selected platform, and atomically writes a `0600` file under the data directory. The HTTP response and logs never include cookie values.

YouTube selection order is: creator-provided Chinese subtitles, other creator-provided subtitles, original-language automatic captions, other automatic captions, then local ASR. English captions are accepted as source material; the configured summary model still produces Chinese Markdown. PO Token requirements vary by YouTube client and yt-dlp version, so EasySourceFlow does not embed a token generator. Follow the current [yt-dlp PO Token Guide](https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide) when the returned status is `youtube_po_token_required`.

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
