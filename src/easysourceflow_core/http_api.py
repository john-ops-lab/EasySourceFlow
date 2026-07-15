"""Small localhost HTTP API for easysourceflowd."""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from . import __version__
from .config import (
    DEFAULT_SUMMARY_PROMPT,
    Settings,
    default_bilibili_cookies_file,
    default_youtube_cookies_file,
    effective_bilibili_cookies_file,
    effective_youtube_cookies_file,
)
from .backup import backup_artifacts
from .errors import EasySourceFlowError
from .maintenance import maintenance_status
from .service import EasySourceFlowService
from .web_ui import delete_favorite, favorite_output, list_favorites, list_outputs, render_index, render_output


logger = logging.getLogger(__name__)
_AGENT_STATUS_LOCK = threading.Lock()
_MAX_SUMMARY_PROMPT_CHARS = 8000

_MODEL_SERVICES = [
    {
        "id": "local",
        "label": "本地兜底",
        "provider": "local",
        "base_url": "",
        "models": ["local_extractive_fallback"],
        "default_model": "local_extractive_fallback",
        "strong_model": "local_extractive_fallback",
    },
    {
        "id": "deepseek",
        "label": "DeepSeek",
        "provider": "openai_compatible",
        "base_url": "https://api.deepseek.com",
        "models": ["deepseek-v4-flash", "deepseek-v4-pro", "deepseek-chat", "deepseek-reasoner"],
        "default_model": "deepseek-v4-flash",
        "strong_model": "deepseek-v4-pro",
    },
    {
        "id": "openai",
        "label": "OpenAI",
        "provider": "openai_compatible",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini"],
        "default_model": "gpt-4.1-mini",
        "strong_model": "gpt-4.1",
    },
    {
        "id": "qwen",
        "label": "通义千问",
        "provider": "openai_compatible",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-plus", "qwen-max", "qwen-turbo", "qwen-long"],
        "default_model": "qwen-plus",
        "strong_model": "qwen-max",
    },
    {
        "id": "kimi",
        "label": "Kimi / Moonshot",
        "provider": "openai_compatible",
        "base_url": "https://api.moonshot.cn/v1",
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k", "kimi-k2-0711-preview"],
        "default_model": "moonshot-v1-8k",
        "strong_model": "kimi-k2-0711-preview",
    },
    {
        "id": "zhipu",
        "label": "智谱 GLM",
        "provider": "openai_compatible",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": ["glm-4-plus", "glm-4-air", "glm-4-flash"],
        "default_model": "glm-4-flash",
        "strong_model": "glm-4-plus",
    },
    {
        "id": "openrouter",
        "label": "OpenRouter",
        "provider": "openai_compatible",
        "base_url": "https://openrouter.ai/api/v1",
        "models": ["openai/gpt-4o-mini", "deepseek/deepseek-chat", "qwen/qwen-2.5-72b-instruct"],
        "default_model": "openai/gpt-4o-mini",
        "strong_model": "deepseek/deepseek-chat",
    },
    {
        "id": "minimax",
        "label": "MiniMax",
        "provider": "openai_compatible",
        "base_url": "https://api.minimaxi.com/v1",
        "models": ["MiniMax-M2.7-highspeed", "MiniMax-M2.7", "MiniMax-M2.5-highspeed", "MiniMax-M2.5"],
        "default_model": "MiniMax-M2.7-highspeed",
        "strong_model": "MiniMax-M2.7",
    },
    {
        "id": "gemini",
        "label": "Google Gemini",
        "provider": "openai_compatible",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "models": ["gemini-3.5-flash", "gemini-3.1-pro-preview", "gemini-2.5-flash", "gemini-2.5-pro"],
        "default_model": "gemini-3.5-flash",
        "strong_model": "gemini-3.1-pro-preview",
    },
    {
        "id": "siliconflow",
        "label": "硅基流动",
        "provider": "openai_compatible",
        "base_url": "https://api.siliconflow.cn/v1",
        "models": ["Qwen/Qwen2.5-72B-Instruct", "Pro/zai-org/GLM-4.7", "deepseek-ai/DeepSeek-V3", "Pro/deepseek-ai/DeepSeek-R1"],
        "default_model": "Qwen/Qwen2.5-72B-Instruct",
        "strong_model": "Pro/zai-org/GLM-4.7",
    },
    {
        "id": "ollama",
        "label": "Ollama（本地）",
        "provider": "openai_compatible",
        "base_url": "http://127.0.0.1:11434/v1",
        "models": ["qwen3:8b", "qwen3:14b", "llama3.3", "deepseek-r1:14b"],
        "default_model": "qwen3:8b",
        "strong_model": "qwen3:14b",
        "requires_api_key": False,
    },
    {
        "id": "lmstudio",
        "label": "LM Studio（本地）",
        "provider": "openai_compatible",
        "base_url": "http://127.0.0.1:1234/v1",
        "models": ["openai/gpt-oss-20b"],
        "default_model": "openai/gpt-oss-20b",
        "strong_model": "openai/gpt-oss-20b",
        "requires_api_key": False,
    },
    {
        "id": "xai",
        "label": "xAI Grok",
        "provider": "openai_compatible",
        "base_url": "https://api.x.ai/v1",
        "models": ["grok-4.5"],
        "default_model": "grok-4.5",
        "strong_model": "grok-4.5",
    },
    {
        "id": "doubao",
        "label": "火山方舟 / 豆包",
        "provider": "openai_compatible",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "models": ["doubao-seed-2-0-lite-260215", "doubao-seed-2-0-pro-260215", "doubao-seed-1-6-250615"],
        "default_model": "doubao-seed-2-0-lite-260215",
        "strong_model": "doubao-seed-2-0-pro-260215",
        "api_style": "responses",
    },
    {
        "id": "qianfan",
        "label": "百度千帆",
        "provider": "openai_compatible",
        "base_url": "https://qianfan.baidubce.com/v2",
        "models": ["ernie-5.0", "ernie-5.0-thinking-preview", "ernie-4.5-turbo-128k", "deepseek-v3.2"],
        "default_model": "ernie-5.0",
        "strong_model": "ernie-5.0-thinking-preview",
    },
    {
        "id": "hunyuan",
        "label": "腾讯混元 / TokenHub",
        "provider": "openai_compatible",
        "base_url": "https://tokenhub.tencentmaas.com/v1",
        "models": ["hy3-preview"],
        "default_model": "hy3-preview",
        "strong_model": "hy3-preview",
    },
]

_MODEL_SERVICE_KEY_NAMES = {
    service["id"]: f"EASYSOURCEFLOW_MODEL_API_KEY_{service['id'].upper()}"
    for service in _MODEL_SERVICES
    if service["id"] != "local"
}


def build_server(settings: Settings) -> ThreadingHTTPServer:
    service = EasySourceFlowService(settings)

    class Handler(BaseHTTPRequestHandler):
        server_version = f"easysourceflowd/{__version__}"

        def log_message(self, format: str, *args: object) -> None:
            logger.info("http request client=%s %s", self.client_address[0], format % args)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            _record_agent_request(settings, self.headers, parsed.path)
            logger.debug("http get", extra={"path": parsed.path})
            if parsed.path == "/favicon.ico":
                self._empty(status=204)
                return
            if parsed.path in {"/", "/ui"}:
                self._html(render_index())
                return
            if parsed.path == "/health":
                self._json({"ok": True, "service": "easysourceflowd", "version": __version__, "runtime": service.health()})
                return
            if parsed.path == "/outputs":
                self._json(list_outputs(settings.output_dir))
                return
            if parsed.path == "/favorites":
                self._json(list_favorites(settings.output_dir))
                return
            if parsed.path == "/search":
                query = parse_qs(parsed.query)
                q = (query.get("q") or [""])[0]
                source = (query.get("source") or [""])[0]
                limit = int((query.get("limit") or ["50"])[0])
                self._json(service.search_outputs(q, source_type=source, limit=limit))
                return
            if parsed.path == "/cookies/bilibili":
                self._json(_bilibili_cookie_status(settings))
                return
            if parsed.path == "/cookies/youtube":
                self._json(_youtube_cookie_status(settings))
                return
            if parsed.path == "/model":
                self._json(_model_status(settings))
                return
            if parsed.path == "/prompt":
                self._json(_prompt_status(settings))
                return
            if parsed.path == "/agent/status":
                self._json(_agent_status(settings))
                return
            if parsed.path == "/maintenance/status":
                self._json(maintenance_status(settings))
                return
            if parsed.path == "/downloads":
                query = parse_qs(parsed.query)
                limit = int((query.get("limit") or ["20"])[0])
                status = (query.get("status") or [None])[0]
                self._json({"items": service.list_media_downloads(limit=limit, status=status)})
                return
            if parsed.path == "/downloads/queue":
                self._json(service.media_download_queue_status())
                return
            download_match = re.fullmatch(r"/downloads/([^/]+)(?:/(file))?", parsed.path)
            if download_match:
                job_id, action = download_match.groups()
                if action == "file":
                    path = service.media_download_file(job_id)
                    if not path:
                        self._json({"error": {"code": "not_found", "message": "Download file not found."}}, status=404)
                        return
                    self._file(path)
                    return
                job = service.get_job(job_id)
                if not job or job.get("request_kind") != "media_download":
                    self._json({"error": {"code": "not_found", "message": "Download job not found."}}, status=404)
                    return
                self._json(job)
                return
            if parsed.path.startswith("/outputs/"):
                status, html = render_output(settings.output_dir, parsed.path[len("/outputs/") :])
                self._html(html, status=status)
                return
            if parsed.path.startswith("/jobs/"):
                job_id = parsed.path.rsplit("/", 1)[-1]
                job = service.get_job(job_id)
                if not job:
                    self._json({"error": {"code": "not_found", "message": "Job not found."}}, status=404)
                    return
                self._json(job)
                return
            if parsed.path.startswith("/batches/"):
                batch_id = parsed.path.rsplit("/", 1)[-1]
                batch = service.get_batch(batch_id)
                if not batch:
                    self._json({"error": {"code": "not_found", "message": "Batch not found."}}, status=404)
                    return
                self._json(batch)
                return
            if parsed.path == "/batches":
                query = parse_qs(parsed.query)
                limit = int((query.get("limit") or ["20"])[0])
                self._json({"items": service.list_batches(limit=limit)})
                return
            if parsed.path == "/jobs":
                query = parse_qs(parsed.query)
                limit = int((query.get("limit") or ["20"])[0])
                status = (query.get("status") or [None])[0]
                self._json({"items": service.list_jobs(limit=limit, status=status)})
                return
            if parsed.path == "/queue":
                self._json(service.queue_status())
                return
            self._json({"error": {"code": "not_found", "message": "Endpoint not found."}}, status=404)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            _record_agent_request(settings, self.headers, parsed.path)
            logger.info("http post path=%s", parsed.path)
            download_action = re.fullmatch(r"/downloads/([^/]+)/(retry|cancel)", parsed.path)
            if download_action:
                job_id, action = download_action.groups()
                job = service.retry_media_download(job_id) if action == "retry" else service.cancel_media_download(job_id)
                if not job:
                    self._json({"error": {"code": "not_found", "message": "Download job not found."}}, status=404)
                    return
                self._json(job)
                return
            if parsed.path.endswith("/retry") and parsed.path.startswith("/jobs/"):
                payload = self._read_json()
                job_id = parsed.path.split("/")[-2]
                job = service.retry_job(
                    job_id,
                    instruction=payload.get("instruction") if "instruction" in payload else None,
                    summary_quality=payload.get("summary_quality") if "summary_quality" in payload else None,
                    force_refresh=bool(payload.get("force_refresh", True)),
                )
                if not job:
                    self._json({"error": {"code": "not_found", "message": "Job not found."}}, status=404)
                    return
                self._json(job)
                return
            if parsed.path.endswith("/cancel") and parsed.path.startswith("/jobs/"):
                job_id = parsed.path.split("/")[-2]
                job = service.cancel_job(job_id)
                if not job:
                    self._json({"error": {"code": "not_found", "message": "Job not found."}}, status=404)
                    return
                self._json(job)
                return
            if parsed.path not in {
                "/jobs",
                "/summarize",
                "/batches",
                "/cleanup",
                "/backup",
                "/documents",
                "/favorites",
                "/favorites/delete",
                "/outputs/open-package",
                "/model",
                "/model/test",
                "/prompt",
                "/bilibili/login/open",
                "/cookies/bilibili/import",
                "/youtube/login/open",
                "/cookies/youtube/import",
                "/downloads",
            }:
                self._json({"error": {"code": "not_found", "message": "Endpoint not found."}}, status=404)
                return
            payload = self._read_json()
            if parsed.path == "/outputs/open-package":
                job = service.get_job(str(payload.get("job_id") or ""))
                package_path = str(((job or {}).get("result") or {}).get("resource_package_path") or "")
                try:
                    self._json(_open_resource_package(settings.output_dir, package_path))
                except FileNotFoundError:
                    self._json({"error": {"code": "not_found", "message": "Resource package not found."}}, status=404)
                except OSError as exc:
                    logger.exception("resource package open failed")
                    self._json({"error": {"code": "open_failed", "message": f"Could not open resource package: {type(exc).__name__}."}}, status=500)
                return
            if parsed.path == "/model":
                try:
                    self._json(_model_update(settings, payload))
                except EasySourceFlowError as exc:
                    self._json({"error": exc.to_dict()}, status=400)
                return
            if parsed.path == "/prompt":
                try:
                    self._json(_prompt_update(settings, payload))
                except EasySourceFlowError as exc:
                    self._json({"error": exc.to_dict()}, status=400)
                return
            if parsed.path == "/favorites":
                try:
                    self._json(favorite_output(settings.output_dir, str(payload.get("relative_path") or "")))
                except FileNotFoundError:
                    self._json({"error": {"code": "not_found", "message": "Output not found."}}, status=404)
                except OSError as exc:
                    logger.exception("favorite copy failed")
                    self._json({"error": {"code": "favorite_failed", "message": f"Could not copy favorite: {type(exc).__name__}."}}, status=500)
                return
            if parsed.path == "/favorites/delete":
                try:
                    self._json(delete_favorite(settings.output_dir, str(payload.get("relative_path") or "")))
                except FileNotFoundError:
                    self._json({"error": {"code": "not_found", "message": "Favorite not found."}}, status=404)
                except OSError as exc:
                    logger.exception("favorite delete failed")
                    self._json({"error": {"code": "favorite_delete_failed", "message": f"Could not delete favorite: {type(exc).__name__}."}}, status=500)
                return
            if parsed.path == "/model/test":
                self._json(_model_test(settings, service))
                return
            if parsed.path == "/bilibili/login/open":
                self._json(_open_bilibili_login())
                return
            if parsed.path == "/cookies/bilibili/import":
                try:
                    self._json(_import_bilibili_cookies(settings))
                except EasySourceFlowError as exc:
                    self._json({"error": exc.to_dict()}, status=400)
                return
            if parsed.path == "/youtube/login/open":
                self._json(_open_youtube_login())
                return
            if parsed.path == "/cookies/youtube/import":
                try:
                    self._json(_import_youtube_cookies(settings))
                except EasySourceFlowError as exc:
                    self._json({"error": exc.to_dict()}, status=400)
                return
            if parsed.path == "/documents":
                try:
                    self._json(service.submit_document_payload(payload, run_async=True))
                except EasySourceFlowError as exc:
                    self._json({"error": exc.to_dict()}, status=400)
                return
            if parsed.path == "/downloads":
                job = service.submit_media_download_async(
                    url=str(payload.get("url") or ""),
                    media_type=str(payload.get("media_type") or ""),
                    format_name=str(payload.get("format") or ""),
                )
                self._json(job)
                return
            if parsed.path == "/cleanup":
                days = int(payload.get("days", 14))
                dry_run = bool(payload.get("dry_run", True))
                self._json(
                    service.cleanup(
                        days=days,
                        dry_run=dry_run,
                        include_temp=bool(payload.get("include_temp", True)),
                        include_outputs=bool(payload.get("include_outputs", True)),
                        include_jobs=bool(payload.get("include_jobs", False)),
                    )
                )
                return
            if parsed.path == "/backup":
                self._json(backup_artifacts(settings))
                return
            if parsed.path == "/batches":
                urls = payload.get("urls") or []
                if not isinstance(urls, list):
                    self._json({"error": {"code": "invalid_request", "message": "urls must be a list."}}, status=400)
                    return
                instruction = str(payload.get("instruction", ""))
                summary_quality = str(payload.get("summary_quality") or "fast")
                batch = service.submit_batch_async(
                    [str(url) for url in urls],
                    instruction=instruction,
                    summary_quality=summary_quality,
                    force_refresh=bool(payload.get("force_refresh", False)),
                )
                self._json(batch)
                return
            url = str(payload.get("url", ""))
            instruction = str(payload.get("instruction", ""))
            summary_quality = str(payload.get("summary_quality") or "fast")
            force_refresh = bool(payload.get("force_refresh", False))
            if parsed.path == "/jobs":
                job = service.submit_link_async(
                    url=url,
                    instruction=instruction,
                    summary_quality=summary_quality,
                    force_refresh=force_refresh,
                )
            else:
                job = service.submit_link(
                    url=url,
                    instruction=instruction,
                    summary_quality=summary_quality,
                    force_refresh=force_refresh,
                )
            status = 200 if job["status"] != "failed" else 400
            self._json(job, status=status)

        def _read_json(self) -> dict:
            length = int(self.headers.get("content-length") or "0")
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            try:
                return json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return {}

        def _json(self, payload: dict, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self._write_body(body)

        def _html(self, payload: str, status: int = 200) -> None:
            body = payload.encode("utf-8")
            self.send_response(status)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self._write_body(body)

        def _file(self, path: Path) -> None:
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            stat = path.stat()
            self.send_response(200)
            self.send_header("content-type", content_type)
            self.send_header("content-length", str(stat.st_size))
            self.send_header("content-disposition", f"attachment; filename*=UTF-8''{quote(path.name)}")
            self.send_header("x-content-type-options", "nosniff")
            self.end_headers()
            try:
                with path.open("rb") as source:
                    shutil.copyfileobj(source, self.wfile, length=1024 * 1024)
            except (BrokenPipeError, ConnectionResetError):
                logger.debug("client disconnected during media download path=%s", path)

        def _write_body(self, body: bytes) -> None:
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                logger.debug("client disconnected before response completed path=%s", self.path)

        def _empty(self, status: int = 204) -> None:
            self.send_response(status)
            self.send_header("content-length", "0")
            self.end_headers()

    return ThreadingHTTPServer((settings.host, settings.port), Handler)


def _bilibili_cookie_status(settings: Settings) -> dict:
    return _cookie_status(
        "Bilibili",
        effective_bilibili_cookies_file(settings),
        default_bilibili_cookies_file(settings),
        {"bilibili.com"},
    )


def _youtube_cookie_status(settings: Settings) -> dict:
    result = _cookie_status(
        "YouTube",
        effective_youtube_cookies_file(settings),
        default_youtube_cookies_file(settings),
        {"youtube.com"},
        auth_cookie_names={"LOGIN_INFO", "SAPISID", "__Secure-1PAPISID", "__Secure-3PAPISID"},
    )
    result["browser_cookie_source"] = settings.youtube_browser_cookie_source
    result["browser_cookie_source_configured"] = bool(settings.youtube_browser_cookie_source.strip())
    if result["browser_cookie_source_configured"]:
        result["ok"] = True
        result["message"] = "Live Chrome login state is configured for YouTube."
    result["extractor_args_configured"] = bool(settings.youtube_extractor_args.strip())
    return result


def _cookie_status(
    label: str,
    path_text: str,
    default_path: Path,
    allowed_domains: set[str],
    auth_cookie_names: set[str] | None = None,
) -> dict:
    result = {
        "configured": bool(path_text),
        "path": path_text or str(default_path),
        "exists": False,
        "size": 0,
        "cookie_count": 0,
        "authenticated": False,
        "updated_at": None,
        "ok": False,
        "message": f"{label} cookies file is not configured.",
    }
    if not path_text:
        return result
    path = Path(path_text).expanduser()
    result["exists"] = path.exists()
    if not path.exists():
        result["message"] = f"{label} cookies file does not exist."
        return result
    stat = path.stat()
    result["size"] = stat.st_size
    result["updated_at"] = datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")
    cookie_count, names = _cookie_file_summary(path, allowed_domains)
    result["cookie_count"] = cookie_count
    result["authenticated"] = bool(names.intersection(auth_cookie_names or set()))
    result["ok"] = cookie_count > 0
    result["message"] = f"{label} cookies file exists." if result["ok"] else f"{label} cookies file has no matching cookies."
    return result


def _prompt_status(settings: Settings) -> dict:
    prompt = settings.summary_prompt.strip() or DEFAULT_SUMMARY_PROMPT
    return {
        "ok": True,
        "prompt": prompt,
        "default_prompt": DEFAULT_SUMMARY_PROMPT,
        "is_default": prompt == DEFAULT_SUMMARY_PROMPT,
        "max_chars": _MAX_SUMMARY_PROMPT_CHARS,
        "automatic_context": [
            "标题、来源、作者、提取方式、字幕状态和来源正文。",
            "网页、微信公众号和视频对应的来源类型补充要求。",
            "来源正文始终按不可信资料处理，不能覆盖总结任务。",
        ],
    }


def _prompt_update(settings: Settings, payload: dict) -> dict:
    prompt = str(payload.get("prompt") or payload.get("system_prompt") or "").strip()
    if len(prompt) < 10:
        raise EasySourceFlowError(
            "invalid_summary_prompt",
            "总结提示词至少需要 10 个字符。",
            ["填写硬性规则和需要模型输出的 Markdown 模板。"],
        )
    if len(prompt) > _MAX_SUMMARY_PROMPT_CHARS:
        raise EasySourceFlowError(
            "invalid_summary_prompt",
            f"总结提示词不能超过 {_MAX_SUMMARY_PROMPT_CHARS} 个字符。",
            ["删除重复示例或把一次性要求放到新总结页面的处理要求中。"],
        )
    path = _summary_prompt_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(prompt + "\n", encoding="utf-8")
    temporary.replace(path)
    try:
        path.chmod(0o600)
    except OSError:
        logger.debug("could not chmod summary prompt file", exc_info=True)
    object.__setattr__(settings, "summary_prompt", prompt)
    object.__setattr__(settings, "summary_prompt_file", path)
    logger.info("summary prompt updated chars=%s", len(prompt))
    return _prompt_status(settings)


def _summary_prompt_path(settings: Settings) -> Path:
    configured = settings.summary_prompt_file
    if str(configured) not in {"", "."}:
        return configured.expanduser()
    return settings.data_dir / "config" / "summary-prompt.txt"


def _record_agent_request(settings: Settings, headers: object, path: str) -> None:
    client = str(getattr(headers, "get", lambda *_: "")("x-easysourceflow-client", "") or "").lower()
    if client != "mcp":
        return
    status_path = settings.data_dir / "agent" / "status.json"
    payload = {
        "client": "mcp",
        "last_seen_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "last_path": path,
    }
    try:
        with _AGENT_STATUS_LOCK:
            status_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = status_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            temporary.replace(status_path)
    except OSError:
        logger.warning("could not persist agent activity", exc_info=True)


def _agent_status(settings: Settings) -> dict:
    mcp_executable = _find_mcp_executable(settings)
    workspace = _agent_workspace(settings)
    skill_path = workspace / "skills" / "easysourceflow" / "SKILL.md" if workspace else None
    skill_installed = bool(skill_path and skill_path.is_file())
    activity = _read_agent_activity(settings)
    recent = False
    if activity.get("last_seen_at"):
        try:
            seen_at = datetime.fromisoformat(str(activity["last_seen_at"]))
            if seen_at.tzinfo is None:
                seen_at = seen_at.astimezone()
            recent = (datetime.now().astimezone() - seen_at).total_seconds() <= 600
        except (TypeError, ValueError):
            pass
    if recent:
        state = "connected"
        message = "最近 10 分钟内收到过 Agent 的 MCP 调用。"
    elif mcp_executable and skill_installed:
        state = "ready"
        message = "MCP 和 Skill 已就绪，尚未检测到最近调用。"
    elif mcp_executable:
        state = "mcp_ready"
        message = "MCP 可用；安装官方 Skill 后可获得完整调用规则。"
    else:
        state = "needs_setup"
        message = "尚未找到 MCP 可执行文件，请先完成本地安装。"
    return {
        "ok": bool(mcp_executable),
        "state": state,
        "message": message,
        "service_url": settings.base_url,
        "mcp": {
            "available": bool(mcp_executable),
            "command": "<PROJECT_ROOT>/.venv/bin/easysourceflow-mcp",
        },
        "skill": {
            "installed": skill_installed,
            "configured": bool(workspace),
        },
        "activity": {
            "recent": recent,
            "last_seen_at": activity.get("last_seen_at"),
            "last_path": activity.get("last_path"),
        },
        "install_command": 'scripts/easysourceflow install-skill "$AGENT_WORKSPACE"',
    }


def _find_mcp_executable(settings: Settings) -> str:
    config_root = _config_file_path().parent
    project_root = Path(__file__).resolve().parents[2]
    candidates = [
        settings.project_root / ".venv" / "bin" / "easysourceflow-mcp",
        config_root / ".venv" / "bin" / "easysourceflow-mcp",
        project_root / ".venv" / "bin" / "easysourceflow-mcp",
    ]
    discovered = shutil.which("easysourceflow-mcp")
    if discovered:
        candidates.insert(0, Path(discovered))
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate.resolve())
    return ""


def _agent_workspace(settings: Settings) -> Path | None:
    if settings.agent_workspace.strip():
        return Path(settings.agent_workspace).expanduser()
    return None


def _read_agent_activity(settings: Settings) -> dict:
    path = settings.data_dir / "agent" / "status.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _model_status(settings: Settings) -> dict:
    whisper_model = Path(settings.whisper_model_path).expanduser()
    active_service = _model_service_for_settings(settings)
    configured_values = _read_env_values(_config_file_path())
    credential_status = {
        service["id"]: bool(configured_values.get(_MODEL_SERVICE_KEY_NAMES.get(service["id"], ""), ""))
        for service in _MODEL_SERVICES
    }
    credential_status["local"] = True
    if settings.model_api_key:
        credential_status[active_service["id"]] = True
    available_models = []
    for service in _MODEL_SERVICES:
        for model in service["models"]:
            if model not in available_models:
                available_models.append(model)
    return {
        "provider": settings.model_provider,
        "model": settings.model,
        "strong_model": settings.strong_model,
        "model_base_url": settings.model_base_url,
        "model_api_key_configured": bool(settings.model_api_key),
        "active_service_id": active_service["id"],
        "credential_status": credential_status,
        "deepseek_base_url": settings.deepseek_base_url,
        "deepseek_api_key_configured": bool(settings.deepseek_api_key),
        "asr": {
            "backend": settings.transcription_backend,
            "max_transcription_seconds": settings.max_transcription_seconds,
            "whisper_cli_path": settings.whisper_cli_path,
            "whisper_model_path": str(whisper_model),
            "whisper_model_exists": whisper_model.exists(),
            "mlx_whisper_path": settings.mlx_whisper_path,
            "faster_whisper_path": settings.faster_whisper_path,
        },
        "document_parsers": _document_parser_status(),
        "editable_in_web": True,
        "config_file": str(_config_file_path()),
        "available_providers": ["local", "openai_compatible", "deepseek"],
        "available_models": available_models,
        "model_services": _MODEL_SERVICES,
        "message": "Model settings can be changed here; API keys are never returned.",
    }


def _model_test(settings: Settings, service: EasySourceFlowService) -> dict:
    health = service.health()
    deepseek = next((item for item in health.get("checks", []) if item.get("name") == "deepseek_api"), None)
    return {"ok": bool(deepseek and deepseek.get("ok")), "check": deepseek, "model": _model_status(settings)}


def _document_parser_status() -> dict:
    try:
        import pypdf  # noqa: F401

        pdf = True
    except Exception:
        pdf = False
    return {
        "text": True,
        "html": True,
        "docx": True,
        "epub": True,
        "pdf": pdf,
    }


def _model_update(settings: Settings, payload: dict) -> dict:
    requested_service_id = str(payload.get("service_id") or "").strip().lower()
    service = _model_service_by_id(requested_service_id) if requested_service_id else None
    if requested_service_id and service is None:
        raise EasySourceFlowError(
            "invalid_model_config",
            "Unsupported model service.",
            ["Choose one of the model services returned by GET /model."],
        )
    provider = str(payload.get("provider") or (service or {}).get("provider") or settings.model_provider).strip().lower()
    model = str(payload.get("model") or settings.model).strip()
    strong_model = str(payload.get("strong_model") or settings.strong_model).strip()
    model_base_url = str(payload.get("model_base_url") or payload.get("deepseek_base_url") or (service or {}).get("base_url") or settings.model_base_url).strip()
    model_api_key = str(payload.get("model_api_key") or payload.get("deepseek_api_key") or "").strip()
    clear_model_api_key = bool(payload.get("clear_model_api_key") or payload.get("clear_deepseek_api_key"))
    if provider not in {"local", "openai_compatible", "deepseek"}:
        raise EasySourceFlowError("invalid_model_config", "Unsupported model provider.", ["Choose local or an OpenAI-compatible provider."])
    if not model:
        raise EasySourceFlowError("invalid_model_config", "Model name cannot be empty.", ["Choose or type a model name."])
    if not strong_model:
        raise EasySourceFlowError("invalid_model_config", "Strong model name cannot be empty.", ["Choose or type a strong model name."])
    if provider != "local" and not model_base_url.startswith(("http://", "https://")):
        raise EasySourceFlowError("invalid_model_config", "Model base URL must start with http:// or https://.", ["Use an official API base URL or a compatible endpoint."])

    service = service or _model_service_for_config(provider, model_base_url)
    service_id = service["id"]
    key_name = _MODEL_SERVICE_KEY_NAMES.get(service_id)
    configured_values = _read_env_values(_config_file_path())
    active_service_id = _model_service_for_settings(settings)["id"]
    if provider == "local" or clear_model_api_key:
        active_api_key = ""
    elif model_api_key:
        active_api_key = model_api_key
    elif key_name and configured_values.get(key_name):
        active_api_key = configured_values[key_name]
    elif service_id == active_service_id:
        active_api_key = settings.model_api_key
    else:
        active_api_key = ""

    values = {
        "EASYSOURCEFLOW_MODEL_PROVIDER": provider,
        "EASYSOURCEFLOW_MODEL": model,
        "EASYSOURCEFLOW_STRONG_MODEL": strong_model,
        "EASYSOURCEFLOW_MODEL_BASE_URL": model_base_url,
        "DEEPSEEK_BASE_URL": model_base_url,
        "EASYSOURCEFLOW_MODEL_API_KEY": active_api_key,
        "DEEPSEEK_API_KEY": active_api_key,
    }
    if key_name and (model_api_key or clear_model_api_key):
        values[key_name] = active_api_key
    config_file = _write_env_values(_config_file_path(), values)
    object.__setattr__(settings, "model_provider", provider)
    object.__setattr__(settings, "model", model)
    object.__setattr__(settings, "strong_model", strong_model)
    object.__setattr__(settings, "deepseek_base_url", model_base_url)
    object.__setattr__(settings, "deepseek_api_key", active_api_key)
    logger.info("model configuration updated service=%s provider=%s model=%s strong_model=%s config_file=%s", service_id, provider, model, strong_model, config_file)
    return {"ok": True, "config_file": str(config_file), "model": _model_status(settings)}


def _model_service_by_id(service_id: str) -> dict | None:
    return next((service for service in _MODEL_SERVICES if service["id"] == service_id), None)


def _model_service_for_config(provider: str, base_url: str) -> dict:
    if provider == "local":
        return _model_service_by_id("local") or _MODEL_SERVICES[0]
    return next(
        (service for service in _MODEL_SERVICES if service["base_url"].rstrip("/") == base_url.rstrip("/")),
        _model_service_by_id("deepseek") or _MODEL_SERVICES[1],
    )


def _model_service_for_settings(settings: Settings) -> dict:
    return _model_service_for_config(settings.model_provider, settings.model_base_url)


def _open_resource_package(output_dir: Path, raw_path: str) -> dict:
    root = output_dir.expanduser().resolve()
    path = Path(raw_path).expanduser().resolve() if raw_path else root / "__missing__"
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise FileNotFoundError(raw_path) from exc
    if not path.is_dir():
        raise FileNotFoundError(raw_path)
    if sys.platform == "darwin":
        command = ["open", str(path)]
    elif shutil.which("xdg-open"):
        command = ["xdg-open", str(path)]
    else:
        raise OSError("No supported desktop file opener is available.")
    subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"ok": True, "resource_package_path": str(path)}


def _open_bilibili_login() -> dict:
    url = "https://passport.bilibili.com/login"
    opened = webbrowser.open(url, new=2)
    return {
        "ok": bool(opened),
        "url": url,
        "message": "Opened the Bilibili login page in the default browser. Sign in to Chrome before importing cookies.",
    }


def _open_youtube_login() -> dict:
    url = "https://www.youtube.com/"
    opened = webbrowser.open(url, new=2)
    return {
        "ok": bool(opened),
        "url": url,
        "message": "Opened YouTube in the default browser. Confirm Chrome is signed in before importing the login state.",
    }


def _import_bilibili_cookies(settings: Settings) -> dict:
    cookies_path = (
        Path(settings.bilibili_cookies_file).expanduser()
        if settings.bilibili_cookies_file
        else default_bilibili_cookies_file(settings)
    )
    _import_browser_cookies(
        settings,
        cookies_path=cookies_path,
        platform="Bilibili",
        test_url="https://www.bilibili.com/",
        allowed_domains={"bilibili.com"},
        error_code="bilibili_cookie_import_failed",
    )
    config_file = _write_env_values(_config_file_path(), {"EASYSOURCEFLOW_BILIBILI_COOKIES_FILE": str(cookies_path)})
    object.__setattr__(settings, "bilibili_cookies_file", str(cookies_path))
    logger.info("bilibili cookies imported path=%s config_file=%s", cookies_path, config_file)
    return {"ok": True, "config_file": str(config_file), "cookies": _bilibili_cookie_status(settings)}


def _import_youtube_cookies(settings: Settings) -> dict:
    cookies_path = (
        Path(settings.youtube_cookies_file).expanduser()
        if settings.youtube_cookies_file
        else default_youtube_cookies_file(settings)
    )
    _import_browser_cookies(
        settings,
        cookies_path=cookies_path,
        platform="YouTube",
        test_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        allowed_domains={"youtube.com"},
        error_code="youtube_cookie_import_failed",
        browser_cookie_source="chrome:Default",
    )
    browser_cookie_source = "chrome:Default"
    config_file = _write_env_values(
        _config_file_path(),
        {
            "EASYSOURCEFLOW_YOUTUBE_COOKIES_FILE": str(cookies_path),
            "EASYSOURCEFLOW_YOUTUBE_BROWSER_COOKIE_SOURCE": browser_cookie_source,
        },
    )
    object.__setattr__(settings, "youtube_cookies_file", str(cookies_path))
    object.__setattr__(settings, "youtube_browser_cookie_source", browser_cookie_source)
    logger.info("youtube browser login configured source=%s snapshot=%s config_file=%s", browser_cookie_source, cookies_path, config_file)
    return {"ok": True, "config_file": str(config_file), "cookies": _youtube_cookie_status(settings)}


def _import_browser_cookies(
    settings: Settings,
    *,
    cookies_path: Path,
    platform: str,
    test_url: str,
    allowed_domains: set[str],
    error_code: str,
    browser_cookie_source: str = "chrome",
) -> None:
    cookies_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        cookies_path.parent.chmod(0o700)
    except OSError:
        logger.debug("could not chmod cookies directory platform=%s", platform, exc_info=True)
    ytdlp = _find_ytdlp(settings)
    with tempfile.TemporaryDirectory(prefix=f"{platform.lower()}-cookies-", dir=str(cookies_path.parent)) as tmpdir:
        raw_path = Path(tmpdir) / "browser-cookies.txt"
        filtered_path = Path(tmpdir) / "filtered-cookies.txt"
        command = [
            ytdlp,
            "--cookies-from-browser",
            browser_cookie_source,
            "--cookies",
            str(raw_path),
            "--skip-download",
            "--simulate",
            "--no-playlist",
            test_url,
        ]
        try:
            completed = subprocess.run(
                command,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=120,
            )
        except subprocess.TimeoutExpired as exc:
            raise EasySourceFlowError(
                error_code,
                f"Timed out while reading {platform} login state from Chrome.",
                ["Keep Chrome installed and unlocked, then retry the import."],
            ) from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip().splitlines()[-1:]
            message = detail[0] if detail else f"Could not import {platform} cookies from Chrome."
            raise EasySourceFlowError(
                error_code,
                message,
                [
                    f"Open Chrome and confirm the {platform} account is signed in.",
                    "Close private browsing windows and retry.",
                    "If Chrome cookies are locked, export a Netscape cookies file manually.",
                ],
            )
        cookie_count = _filter_cookie_file(raw_path, filtered_path, allowed_domains)
        if cookie_count <= 0:
            raise EasySourceFlowError(
                error_code,
                f"Chrome did not provide any {platform} cookies.",
                [f"Open {platform} in Chrome, sign in, and retry the import."],
            )
        filtered_path.replace(cookies_path)
    try:
        cookies_path.chmod(0o600)
    except OSError:
        logger.debug("could not chmod cookies file platform=%s", platform, exc_info=True)


def _filter_cookie_file(source: Path, destination: Path, allowed_domains: set[str]) -> int:
    if not source.exists():
        return 0
    allowed = {domain.lower().lstrip(".") for domain in allowed_domains}
    rows = []
    for raw in source.read_text(encoding="utf-8", errors="replace").splitlines():
        fields = _cookie_fields(raw)
        if not fields:
            continue
        domain = fields[0].lower().lstrip(".")
        if any(domain == item or domain.endswith("." + item) for item in allowed):
            rows.append(raw)
    if not rows:
        return 0
    destination.write_text("# Netscape HTTP Cookie File\n" + "\n".join(rows) + "\n", encoding="utf-8")
    destination.chmod(0o600)
    return len(rows)


def _cookie_file_summary(path: Path, allowed_domains: set[str]) -> tuple[int, set[str]]:
    if not path.exists():
        return 0, set()
    allowed = {domain.lower().lstrip(".") for domain in allowed_domains}
    names = set()
    count = 0
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        fields = _cookie_fields(raw)
        if not fields:
            continue
        domain = fields[0].lower().lstrip(".")
        if not any(domain == item or domain.endswith("." + item) for item in allowed):
            continue
        count += 1
        names.add(fields[5])
    return count, names


def _cookie_fields(raw: str) -> list[str] | None:
    line = raw
    if line.startswith("#HttpOnly_"):
        line = line[len("#HttpOnly_") :]
    elif not line or line.startswith("#"):
        return None
    fields = line.split("\t")
    return fields if len(fields) >= 7 else None


def _find_ytdlp(settings: Settings) -> str:
    candidates = []
    if settings.ytdlp_path:
        candidates.append(settings.ytdlp_path)
    which = shutil.which("yt-dlp")
    if which:
        candidates.append(which)
    project_root = Path(__file__).resolve().parents[2]
    candidates.append(str(project_root / ".venv" / "bin" / "yt-dlp"))
    for candidate in candidates:
        if candidate and Path(candidate).expanduser().exists():
            return str(Path(candidate).expanduser())
    raise EasySourceFlowError(
        "dependency_missing",
        "yt-dlp is required to import Bilibili cookies.",
        ["Install yt-dlp in the EasySourceFlow environment, then retry."],
    )


def _config_file_path() -> Path:
    configured_path = os.environ.get("EASYSOURCEFLOW_CONFIG_FILE", "").strip()
    if configured_path:
        return Path(configured_path).expanduser()
    return Path(__file__).resolve().parents[2] / ".env"


def _write_env_values(path: Path, values: dict[str, str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = dict(values)
    updated: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or "=" not in raw:
            updated.append(raw)
            continue
        key = raw.split("=", 1)[0].strip()
        if key in remaining:
            updated.append(_env_line(key, remaining.pop(key)))
        else:
            updated.append(raw)
    if remaining and updated and updated[-1].strip():
        updated.append("")
    for key, value in remaining.items():
        updated.append(_env_line(key, value))
    path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        logger.debug("could not chmod config file", exc_info=True)
    return path


def _read_env_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _env_line(key: str, value: str) -> str:
    if re.match(r"^[A-Za-z0-9_./:@%+-]*$", value):
        return f"{key}={value}"
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'{key}="{escaped}"'
