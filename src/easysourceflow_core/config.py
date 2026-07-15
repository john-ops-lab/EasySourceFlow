"""Runtime configuration for the EasySourceFlow."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_SUMMARY_PROMPT = (
    "请根据来源内容生成中文 Markdown 总结。\n\n"
    "硬性规则：\n"
    "- 只根据来源内容总结，不要补充外部事实。\n"
    "- 如果内容来自字幕或转写，要先判断它是否像完整内容；如果明显残缺或噪声很重，要在“质量检查”中说明。\n"
    "- 质量检查必须依据“提取方式”和“字幕状态”写，不要猜测来源。\n"
    "- 不要照抄长段原文；可引用摘录只保留短摘录或高度概括。\n"
    "- 不要输出寒暄、免责声明或与模板无关的段落。\n\n"
    "Markdown 模板要求：\n"
    "## 一句话结论\n"
    "用 1-2 句话说明最重要的结论。\n\n"
    "## 核心要点\n"
    "列出 5-8 条具体要点。\n\n"
    "## 详细笔记\n"
    "按主题分组整理关键论据、例子、步骤、人物、数据或上下文。\n\n"
    "## 可引用摘录\n"
    "给出 3-5 条短摘录或可复述的关键表达；来源质量不足时写“无可靠摘录”。\n\n"
    "## 行动项或启发\n"
    "有实践价值时列出可执行动作，否则写“无明确行动项”。\n\n"
    "## 适合沉淀吗\n"
    "给出适合、不适合或有条件适合，并说明原因。\n\n"
    "## 推荐标签\n"
    "给出 3-8 个不含空格的短标签。\n\n"
    "## 质量检查\n"
    "根据提取方式和字幕状态说明来源质量及明显不确定性。"
)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _bool_env(name: str, default: bool = False) -> bool:
    value = _env(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    data_dir: Path
    database_path: Path
    output_dir: Path
    allow_local_urls: bool
    request_timeout_seconds: float
    max_content_chars: int
    ytdlp_path: str
    bilibili_cookies_file: str
    youtube_cookies_file: str
    youtube_extractor_args: str
    ffmpeg_path: str
    whisper_cli_path: str
    whisper_model_path: str
    transcription_backend: str
    mlx_whisper_path: str
    faster_whisper_path: str
    max_transcription_seconds: int
    model_provider: str
    model: str
    strong_model: str
    deepseek_api_key: str
    deepseek_base_url: str
    youtube_browser_cookie_source: str = ""
    cache_ttl_seconds: int = 604800
    notification_webhook_url: str = ""
    notification_webhook_token: str = ""
    notification_command: str = ""
    notification_events: str = ""
    summary_prompt: str = DEFAULT_SUMMARY_PROMPT
    summary_prompt_file: Path = Path()
    agent_workspace: str = ""
    project_root: Path = Path()

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def model_api_key(self) -> str:
        return self.deepseek_api_key

    @property
    def model_base_url(self) -> str:
        return self.deepseek_base_url


def default_bilibili_cookies_file(settings: Settings) -> Path:
    return settings.data_dir / "secrets" / "bilibili-cookies.txt"


def effective_bilibili_cookies_file(settings: Settings) -> str:
    if settings.bilibili_cookies_file:
        return settings.bilibili_cookies_file
    default_path = default_bilibili_cookies_file(settings)
    return str(default_path) if default_path.exists() else ""


def default_youtube_cookies_file(settings: Settings) -> Path:
    return settings.data_dir / "secrets" / "youtube-cookies.txt"


def effective_youtube_cookies_file(settings: Settings) -> str:
    if settings.youtube_cookies_file:
        return settings.youtube_cookies_file
    default_path = default_youtube_cookies_file(settings)
    return str(default_path) if default_path.exists() else ""


def load_settings() -> Settings:
    _load_env_file()
    data_dir = Path(
        os.environ.get(
            "EASYSOURCEFLOW_DATA_DIR",
            str(Path.home() / ".local" / "share" / "easysourceflow"),
        )
    ).expanduser()
    database_path = Path(
        _env("EASYSOURCEFLOW_DATABASE", str(data_dir / "easysourceflow.sqlite3"))
    ).expanduser()
    output_dir = Path(_env("EASYSOURCEFLOW_OUTPUT_DIR", str(data_dir / "output"))).expanduser()
    summary_prompt_file = Path(
        _env(
            "EASYSOURCEFLOW_SUMMARY_PROMPT_FILE",
            str(data_dir / "config" / "summary-prompt.txt"),
        )
    ).expanduser()
    summary_prompt = _env(
        "EASYSOURCEFLOW_SUMMARY_PROMPT",
        _env("EASYSOURCEFLOW_SUMMARY_SYSTEM_PROMPT", DEFAULT_SUMMARY_PROMPT),
    ).strip()
    if summary_prompt_file.is_file():
        saved_prompt = summary_prompt_file.read_text(encoding="utf-8").strip()
        if saved_prompt:
            summary_prompt = saved_prompt

    return Settings(
        host=_env("EASYSOURCEFLOW_HOST", "127.0.0.1"),
        port=int(_env("EASYSOURCEFLOW_PORT", "8765")),
        data_dir=data_dir,
        database_path=database_path,
        output_dir=output_dir,
        allow_local_urls=_bool_env("EASYSOURCEFLOW_ALLOW_LOCAL_URLS", False),
        request_timeout_seconds=float(_env("EASYSOURCEFLOW_REQUEST_TIMEOUT", "20")),
        max_content_chars=int(_env("EASYSOURCEFLOW_MAX_CONTENT_CHARS", "120000")),
        ytdlp_path=_env("EASYSOURCEFLOW_YTDLP_PATH", ""),
        bilibili_cookies_file=_env("EASYSOURCEFLOW_BILIBILI_COOKIES_FILE", ""),
        youtube_cookies_file=_env("EASYSOURCEFLOW_YOUTUBE_COOKIES_FILE", ""),
        youtube_extractor_args=_env("EASYSOURCEFLOW_YOUTUBE_EXTRACTOR_ARGS", ""),
        ffmpeg_path=_env("EASYSOURCEFLOW_FFMPEG_PATH", "ffmpeg"),
        whisper_cli_path=_env("EASYSOURCEFLOW_WHISPER_CLI_PATH", "whisper-cli"),
        whisper_model_path=_env("EASYSOURCEFLOW_WHISPER_MODEL_PATH", str(data_dir / "models" / "ggml-base.bin")),
        transcription_backend=_env("EASYSOURCEFLOW_TRANSCRIPTION_BACKEND", "whisper_cpp"),
        mlx_whisper_path=_env("EASYSOURCEFLOW_MLX_WHISPER_PATH", "mlx_whisper"),
        faster_whisper_path=_env("EASYSOURCEFLOW_FASTER_WHISPER_PATH", "faster-whisper"),
        max_transcription_seconds=int(_env("EASYSOURCEFLOW_MAX_TRANSCRIPTION_SECONDS", "7200")),
        model_provider=_env("EASYSOURCEFLOW_MODEL_PROVIDER", "local"),
        model=_env("EASYSOURCEFLOW_MODEL", "deepseek-v4-flash"),
        strong_model=_env("EASYSOURCEFLOW_STRONG_MODEL", "deepseek-v4-pro"),
        deepseek_api_key=os.environ.get("EASYSOURCEFLOW_MODEL_API_KEY") or os.environ.get("DEEPSEEK_API_KEY", ""),
        deepseek_base_url=os.environ.get("EASYSOURCEFLOW_MODEL_BASE_URL") or os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        youtube_browser_cookie_source=_env("EASYSOURCEFLOW_YOUTUBE_BROWSER_COOKIE_SOURCE", ""),
        cache_ttl_seconds=max(0, int(_env("EASYSOURCEFLOW_CACHE_TTL_SECONDS", "604800"))),
        notification_webhook_url=_env("EASYSOURCEFLOW_NOTIFICATION_WEBHOOK_URL", ""),
        notification_webhook_token=_env("EASYSOURCEFLOW_NOTIFICATION_WEBHOOK_TOKEN", ""),
        notification_command=_env("EASYSOURCEFLOW_NOTIFICATION_COMMAND", ""),
        notification_events=_env("EASYSOURCEFLOW_NOTIFICATION_EVENTS", ""),
        summary_prompt=summary_prompt,
        summary_prompt_file=summary_prompt_file,
        agent_workspace=_env("EASYSOURCEFLOW_AGENT_WORKSPACE", ""),
        project_root=Path(_env("EASYSOURCEFLOW_PROJECT_ROOT", str(Path(__file__).resolve().parents[2]))).expanduser(),
    )


def _load_env_file() -> None:
    configured_path = _env("EASYSOURCEFLOW_CONFIG_FILE", "").strip()
    if configured_path:
        env_path = Path(configured_path).expanduser()
    else:
        env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists() or not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
