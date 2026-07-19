"""Runtime health checks for EasySourceFlow dependencies."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .config import Settings, effective_bilibili_cookies_file, effective_youtube_cookies_file
from .digest import _model_api_ready, _model_response_text, _uses_responses_api


def run_health_checks(settings: Settings) -> dict:
    checks = [
        _check_data_dir(settings),
        _check_deepseek(settings),
        _check_ytdlp(settings),
        _check_ffmpeg(settings),
        _check_whisper(settings),
        _check_transcription_backend(settings),
        _check_document_parsers(),
        _check_pdf_ocr(),
        _check_bilibili_cookies(settings),
        _check_youtube_cookies(settings),
        _check_wechat_extractor(),
    ]
    ok = all(item["ok"] for item in checks if item["required"])
    return {"ok": ok, "checks": checks}


def main() -> None:
    from .config import load_settings

    result = run_health_checks(load_settings())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)


def _check_data_dir(settings: Settings) -> dict:
    try:
        settings.output_dir.mkdir(parents=True, exist_ok=True)
        probe = settings.output_dir / ".healthcheck"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return _result("output_dir", True, "Output directory is writable.", required=True)
    except Exception as exc:
        return _result(
            "output_dir",
            False,
            f"Output directory is not writable: {type(exc).__name__}.",
            required=True,
            fix="Check EASYSOURCEFLOW_OUTPUT_DIR permissions or choose a writable output directory.",
        )


def _check_deepseek(settings: Settings) -> dict:
    provider = settings.model_provider.lower()
    if provider not in {"deepseek", "openai_compatible"}:
        return _result("deepseek_api", True, "External model API is not the active provider.", required=False)
    if not _model_api_ready(settings):
        return _result("deepseek_api", False, "Model API key is not configured.", required=True, fix="Add EASYSOURCEFLOW_MODEL_API_KEY to .env or configure it in Web.")
    uses_responses_api = _uses_responses_api(settings)
    payload = {"model": settings.model}
    model_host = (urlparse(settings.model_base_url).hostname or "").lower()
    if uses_responses_api:
        payload.update({"input": "只回复 ok", "max_output_tokens": 128})
    else:
        completion_token_hosts = {"api.openai.com", "api.minimax.io", "api.minimaxi.com"}
        token_limit_key = "max_completion_tokens" if model_host in completion_token_hosts else "max_tokens"
        payload.update({"messages": [{"role": "user", "content": "只回复 ok"}], token_limit_key: 128})
        if model_host == "api.deepseek.com":
            payload["thinking"] = {"type": "disabled"}
        elif model_host in {"api.minimax.io", "api.minimaxi.com"}:
            payload["reasoning_split"] = True
    headers = {"content-type": "application/json"}
    if settings.model_api_key:
        headers["authorization"] = "Bearer " + settings.model_api_key
    request = Request(
        settings.model_base_url.rstrip("/") + ("/responses" if uses_responses_api else "/chat/completions"),
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
        content = _model_response_text(data) if isinstance(data, dict) else ""
        if content:
            return _result("deepseek_api", True, "Model API is reachable.", required=True)
        if isinstance(data, dict) and _has_model_generation_evidence(data):
            return _result(
                "deepseek_api",
                True,
                "Model API is reachable; the short probe returned reasoning output.",
                required=True,
            )
        error = data.get("error") if isinstance(data, dict) else None
        message = error.get("message") if isinstance(error, dict) else "Model API response did not include a chat completion."
        return _result("deepseek_api", False, f"Model API check failed: {message}", required=True, fix="Check API key validity, model name, quota, and EASYSOURCEFLOW_MODEL_BASE_URL.")
    except Exception as exc:
        return _result("deepseek_api", False, f"Model API check failed: {type(exc).__name__}.", required=True, fix="Check network access, API quota, EASYSOURCEFLOW_MODEL_BASE_URL, and EASYSOURCEFLOW_MODEL_API_KEY.")


def _has_model_generation_evidence(data: dict) -> bool:
    choices = data.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message")
            if isinstance(message, dict):
                if any(
                    _non_empty_generation_value(message.get(key))
                    for key in ("reasoning_content", "reasoning_details", "reasoning")
                ):
                    return True
    output = data.get("output")
    if isinstance(output, list) and any(isinstance(item, dict) and item.get("type") == "reasoning" for item in output):
        return True
    usage = data.get("usage")
    if isinstance(usage, dict):
        for key in ("completion_tokens_details", "output_tokens_details"):
            details = usage.get(key)
            if isinstance(details, dict):
                reasoning_tokens = details.get("reasoning_tokens")
                if isinstance(reasoning_tokens, (int, float)) and reasoning_tokens > 0:
                    return True
    return False


def _non_empty_generation_value(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    return isinstance(value, (list, dict)) and bool(value)


def _check_ytdlp(settings: Settings) -> dict:
    path = settings.ytdlp_path or shutil.which("yt-dlp")
    if not path:
        project_ytdlp = Path(__file__).resolve().parents[2] / ".venv" / "bin" / "yt-dlp"
        path = str(project_ytdlp) if project_ytdlp.exists() else ""
    return _executable_version("yt_dlp", path, ["--version"], required=True)


def _check_ffmpeg(settings: Settings) -> dict:
    path = shutil.which(settings.ffmpeg_path) or settings.ffmpeg_path
    return _executable_version("ffmpeg", path, ["-version"], required=True)


def _check_whisper(settings: Settings) -> dict:
    model_path = Path(settings.whisper_model_path).expanduser()
    if not model_path.exists():
        return _result("whisper_model", False, f"Whisper model not found: {model_path}", required=False, fix="Download the whisper.cpp model or update EASYSOURCEFLOW_WHISPER_MODEL_PATH.")
    path = shutil.which(settings.whisper_cli_path) or settings.whisper_cli_path
    executable = _executable_version("whisper_cli", path, ["--help"], required=False, accepted_returncodes={0})
    if not executable["ok"]:
        return executable
    return _result("whisper", True, "Whisper CLI and model are available.", required=False)


def _check_bilibili_cookies(settings: Settings) -> dict:
    cookies_file = effective_bilibili_cookies_file(settings)
    if not cookies_file:
        return _result("bilibili_cookies", False, "Bilibili cookies file is not configured.", required=False, fix="Export Bilibili cookies to a local file and set EASYSOURCEFLOW_BILIBILI_COOKIES_FILE.")
    path = Path(cookies_file).expanduser()
    if not path.exists():
        return _result("bilibili_cookies", False, f"Bilibili cookies file does not exist: {path}", required=False, fix="Update EASYSOURCEFLOW_BILIBILI_COOKIES_FILE or re-export the cookies file.")
    if path.stat().st_size == 0:
        return _result("bilibili_cookies", False, "Bilibili cookies file is empty.", required=False, fix="Re-export cookies; do not paste cookie contents into chat or logs.")
    return _result("bilibili_cookies", True, "Bilibili cookies file exists.", required=False)


def _check_youtube_cookies(settings: Settings) -> dict:
    if settings.youtube_browser_cookie_source.strip():
        return _result(
            "youtube_cookies",
            True,
            "Live Chrome login state is configured for YouTube.",
            required=False,
        )
    cookies_file = effective_youtube_cookies_file(settings)
    if not cookies_file:
        return _result(
            "youtube_cookies",
            False,
            "YouTube cookies file is not configured.",
            required=False,
            fix="Log in to YouTube in Chrome, then import the login state from Web maintenance.",
        )
    path = Path(cookies_file).expanduser()
    if not path.exists():
        return _result(
            "youtube_cookies",
            False,
            f"YouTube cookies file does not exist: {path}",
            required=False,
            fix="Update EASYSOURCEFLOW_YOUTUBE_COOKIES_FILE or import the Chrome login state again.",
        )
    if path.stat().st_size == 0:
        return _result(
            "youtube_cookies",
            False,
            "YouTube cookies file is empty.",
            required=False,
            fix="Import the Chrome login state again; do not paste cookie contents into chat or logs.",
        )
    return _result("youtube_cookies", True, "YouTube cookies file exists.", required=False)


def _check_wechat_extractor() -> dict:
    command = os.environ.get("EASYSOURCEFLOW_WECHAT_MARKDOWN_COMMAND", "").strip()
    if command:
        return _result("wechat_external_extractor", True, "External WeChat extractor command is configured.", required=False)
    try:
        import playwright  # noqa: F401
        configured_chrome = os.environ.get("EASYSOURCEFLOW_CHROME_PATH", "").strip()
        chrome_path = Path(configured_chrome).expanduser() if configured_chrome else Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        if chrome_path.exists():
            return _result("wechat_browser_fallback", True, "Playwright package and system Chrome are available.", required=False)
        return _result("wechat_browser_fallback", True, "Playwright package is available.", required=False)
    except Exception:
        return _result(
            "wechat_browser_fallback",
            False,
            "Using built-in lightweight WeChat extractor; Playwright fallback is not installed.",
            required=False,
            fix="Install Playwright Python package and keep Google Chrome installed for dynamic WeChat pages.",
        )


def _check_transcription_backend(settings: Settings) -> dict:
    backend = settings.transcription_backend.strip().lower()
    if backend == "mlx_whisper":
        path = shutil.which(settings.mlx_whisper_path) or settings.mlx_whisper_path
        return _result("transcription_backend", bool(path and Path(path).exists()), "Configured backend: mlx_whisper.", required=False, fix="Install mlx_whisper or switch EASYSOURCEFLOW_TRANSCRIPTION_BACKEND to whisper_cpp.")
    if backend == "faster_whisper":
        path = shutil.which(settings.faster_whisper_path) or settings.faster_whisper_path
        return _result("transcription_backend", bool(path and Path(path).exists()), "Configured backend: faster_whisper.", required=False, fix="Install faster-whisper or switch EASYSOURCEFLOW_TRANSCRIPTION_BACKEND to whisper_cpp.")
    return _result("transcription_backend", True, "Configured backend: whisper_cpp.", required=False)


def _check_document_parsers() -> dict:
    try:
        import pypdf  # noqa: F401

        return _result("document_parsers", True, "Text, HTML, DOCX, EPUB, and PDF uploads are supported.", required=False)
    except Exception:
        return _result(
            "document_parsers",
            False,
            "Text, HTML, DOCX, and EPUB uploads are supported; PDF extraction needs pypdf.",
            required=False,
            fix="Install pypdf in the active runtime, then restart EasySourceFlow.",
        )


def _check_pdf_ocr() -> dict:
    helper = Path(__file__).with_name("macos_pdf_ocr.swift")
    if sys.platform == "darwin" and shutil.which("xcrun") and helper.is_file():
        return _result("pdf_ocr", True, "macOS Vision OCR is available for image-only PDFs.", required=False)
    return _result(
        "pdf_ocr",
        False,
        "Image-only PDF OCR is unavailable; searchable PDFs still work.",
        required=False,
        fix="On macOS, install the Xcode Command Line Tools. On other systems, OCR the PDF before uploading it.",
    )


def _executable_version(name: str, path: str, args: list[str], required: bool, accepted_returncodes: set[int] | None = None) -> dict:
    if not path:
        return _result(name, False, f"{name} executable was not found.", required=required, fix=_dependency_fix(name))
    accepted = accepted_returncodes or {0, 1}
    try:
        completed = subprocess.run(
            [path, *args],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
    except Exception as exc:
        return _result(name, False, f"{name} check failed: {type(exc).__name__}.", required=required, fix=_dependency_fix(name))
    if completed.returncode not in accepted:
        return _result(name, False, f"{name} returned exit code {completed.returncode}.", required=required, fix=_dependency_fix(name))
    first_line = (completed.stdout or completed.stderr or "").strip().splitlines()[:1]
    detail = first_line[0] if first_line else f"{name} is available."
    return _result(name, True, detail, required=required)


def _result(name: str, ok: bool, message: str, required: bool, fix: str = "") -> dict:
    result = {"name": name, "ok": ok, "required": required, "message": message}
    if fix and not ok:
        result["fix"] = fix
    return result


def _dependency_fix(name: str) -> str:
    if name == "yt_dlp":
        return "Run scripts/easysourceflow install-launchd or install yt-dlp in the active Python environment."
    if name == "ffmpeg":
        return "Install ffmpeg with Homebrew, then rerun scripts/easysourceflow install-launchd."
    if name == "whisper_cli":
        return "Install whisper.cpp/whisper-cli and set EASYSOURCEFLOW_WHISPER_CLI_PATH if needed."
    return "Install the missing executable or set the matching EASYSOURCEFLOW_* path."


if __name__ == "__main__":
    main()
