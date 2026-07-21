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
import time
import webbrowser
from dataclasses import replace
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
from .health import run_model_check
from .maintenance import maintenance_status
from .model_catalog import model_catalog
from .model_services import (
    MODEL_FALLBACK_SERVICE_KEY,
    MODEL_SERVICES as _MODEL_SERVICES,
    MODEL_SERVICE_KEY_NAMES as _MODEL_SERVICE_KEY_NAMES,
    configured_model_profiles,
    model_profile_enabled_env_values,
    model_profile_env_values,
    model_service_by_id,
    model_service_for_config,
    model_service_is_configured,
)
from .service import EasySourceFlowService
from .url_utils import DEFAULT_FAKE_IP_CIDRS, normalize_fake_ip_cidrs
from .web_ui import delete_favorite, favorite_output, list_favorites, list_outputs, render_index, render_output


logger = logging.getLogger(__name__)
_AGENT_STATUS_LOCK = threading.Lock()
_CONFIG_FILE_LOCK = threading.Lock()
_MAX_SUMMARY_PROMPT_CHARS = 8000
_BILIBILI_AUTH_COOKIE_NAMES = {"SESSDATA", "bili_jct", "DedeUserID"}
_YOUTUBE_AUTH_COOKIE_NAMES = {"LOGIN_INFO", "SAPISID", "__Secure-1PAPISID", "__Secure-3PAPISID"}
_LOGIN_AUTO_IMPORT_TIMEOUT_SECONDS = 300
_LOGIN_AUTO_IMPORT_RETRY_SECONDS = (3, 5, 8, 12, 15)

class _LoginImportCoordinator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = threading.Lock()
        self._import_locks = {"bilibili": threading.Lock(), "youtube": threading.Lock()}
        self._threads: dict[str, threading.Thread] = {}
        self._stop_events: dict[str, threading.Event] = {}
        self._states = {platform: self._new_state() for platform in self._import_locks}

    def start(self, platform: str) -> dict:
        with self._lock:
            thread = self._threads.get(platform)
            stop_event = self._stop_events.get(platform)
            if thread and thread.is_alive() and stop_event and not stop_event.is_set():
                return dict(self._states[platform])
            now = datetime.now().isoformat(timespec="seconds")
            self._states[platform] = {
                "status": "waiting",
                "attempts": 0,
                "started_at": now,
                "updated_at": now,
                "last_error": "",
            }
            stop_event = threading.Event()
            self._stop_events[platform] = stop_event
            thread = threading.Thread(
                target=self._run,
                args=(platform, stop_event),
                name=f"{platform}-login-auto-import",
                daemon=True,
            )
            self._threads[platform] = thread
            thread.start()
            return dict(self._states[platform])

    def status(self, platform: str) -> dict:
        with self._lock:
            return dict(self._states[platform])

    def import_now(self, platform: str) -> dict:
        try:
            return self._attempt(platform)
        except EasySourceFlowError as exc:
            self._update(platform, "failed", last_error=exc.message)
            raise

    def disconnect(self, platform: str) -> dict:
        with self._lock:
            stop_event = self._stop_events.get(platform)
            if stop_event:
                stop_event.set()
        with self._import_locks[platform]:
            result = (
                _disconnect_bilibili_login(self.settings)
                if platform == "bilibili"
                else _disconnect_youtube_login(self.settings)
            )
        with self._lock:
            self._states[platform] = self._new_state()
            result["auto_import"] = dict(self._states[platform])
        return result

    def _run(self, platform: str, stop_event: threading.Event) -> None:
        deadline = time.monotonic() + _LOGIN_AUTO_IMPORT_TIMEOUT_SECONDS
        retry_index = 0
        while not stop_event.is_set() and time.monotonic() < deadline:
            try:
                self._attempt(platform)
                return
            except EasySourceFlowError as exc:
                if stop_event.is_set():
                    return
                if not exc.code.endswith("_login_not_ready"):
                    self._update(platform, "failed", last_error=exc.message)
                    return
                self._update(platform, "waiting", last_error=exc.message)
            delay = _LOGIN_AUTO_IMPORT_RETRY_SECONDS[
                min(retry_index, len(_LOGIN_AUTO_IMPORT_RETRY_SECONDS) - 1)
            ]
            retry_index += 1
            stop_event.wait(min(delay, max(0, deadline - time.monotonic())))
        if not stop_event.is_set():
            self._update(platform, "timed_out", last_error="Login was not detected within five minutes.")

    def _attempt(self, platform: str) -> dict:
        with self._import_locks[platform]:
            self._update(platform, "importing", increment_attempts=True)
            result = (
                _import_bilibili_cookies(self.settings)
                if platform == "bilibili"
                else _import_youtube_cookies(self.settings)
            )
            self._update(platform, "succeeded", last_error="")
            result["auto_import"] = self.status(platform)
            return result

    def _update(self, platform: str, status: str, *, last_error: str = "", increment_attempts: bool = False) -> None:
        with self._lock:
            state = self._states[platform]
            state["status"] = status
            state["updated_at"] = datetime.now().isoformat(timespec="seconds")
            state["last_error"] = last_error
            if increment_attempts:
                state["attempts"] += 1

    @staticmethod
    def _new_state() -> dict:
        return {"status": "idle", "attempts": 0, "started_at": None, "updated_at": None, "last_error": ""}


def build_server(settings: Settings) -> ThreadingHTTPServer:
    service = EasySourceFlowService(settings)
    login_imports = _LoginImportCoordinator(settings)

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
                result = _bilibili_cookie_status(settings)
                result["auto_import"] = login_imports.status("bilibili")
                self._json(result)
                return
            if parsed.path == "/cookies/youtube":
                result = _youtube_cookie_status(settings)
                result["auto_import"] = login_imports.status("youtube")
                self._json(result)
                return
            if parsed.path == "/model":
                self._json(_model_status(settings))
                return
            if parsed.path == "/prompt":
                self._json(_prompt_status(settings))
                return
            if parsed.path == "/network/security":
                self._json(_network_security_status(settings))
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
                "/model/credentials",
                "/model/credentials/delete",
                "/model/catalog",
                "/model/test",
                "/prompt",
                "/network/security",
                "/bilibili/login/open",
                "/cookies/bilibili/import",
                "/cookies/bilibili/logout",
                "/youtube/login/open",
                "/cookies/youtube/import",
                "/cookies/youtube/logout",
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
            if parsed.path in {"/model/credentials", "/model/credentials/delete"}:
                try:
                    self._json(
                        _model_credential_update(
                            settings,
                            payload,
                            delete=parsed.path.endswith("/delete"),
                        )
                    )
                except EasySourceFlowError as exc:
                    self._json({"error": exc.to_dict()}, status=400)
                return
            if parsed.path == "/model/catalog":
                try:
                    self._json(_model_catalog_status(settings, payload))
                except EasySourceFlowError as exc:
                    self._json({"error": exc.to_dict()}, status=400)
                return
            if parsed.path == "/prompt":
                try:
                    self._json(_prompt_update(settings, payload))
                except EasySourceFlowError as exc:
                    self._json({"error": exc.to_dict()}, status=400)
                return
            if parsed.path == "/network/security":
                try:
                    self._json(_network_security_update(settings, payload))
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
                try:
                    self._json(_model_test(settings, payload))
                except EasySourceFlowError as exc:
                    self._json({"error": exc.to_dict()}, status=400)
                return
            if parsed.path == "/bilibili/login/open":
                result = _open_bilibili_login()
                if result["ok"] and payload.get("auto_import", True):
                    result["auto_import"] = login_imports.start("bilibili")
                self._json(result)
                return
            if parsed.path == "/cookies/bilibili/import":
                try:
                    self._json(login_imports.import_now("bilibili"))
                except EasySourceFlowError as exc:
                    self._json({"error": exc.to_dict()}, status=400)
                return
            if parsed.path == "/cookies/bilibili/logout":
                self._json(login_imports.disconnect("bilibili"))
                return
            if parsed.path == "/youtube/login/open":
                result = _open_youtube_login()
                if result["ok"] and payload.get("auto_import", True):
                    result["auto_import"] = login_imports.start("youtube")
                self._json(result)
                return
            if parsed.path == "/cookies/youtube/import":
                try:
                    self._json(login_imports.import_now("youtube"))
                except EasySourceFlowError as exc:
                    self._json({"error": exc.to_dict()}, status=400)
                return
            if parsed.path == "/cookies/youtube/logout":
                self._json(login_imports.disconnect("youtube"))
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
        auth_cookie_names=_BILIBILI_AUTH_COOKIE_NAMES,
    )


def _youtube_cookie_status(settings: Settings) -> dict:
    result = _cookie_status(
        "YouTube",
        effective_youtube_cookies_file(settings),
        default_youtube_cookies_file(settings),
        {"youtube.com"},
        auth_cookie_names=_YOUTUBE_AUTH_COOKIE_NAMES,
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
    result["ok"] = result["authenticated"] if auth_cookie_names else cookie_count > 0
    if result["ok"]:
        result["message"] = f"{label} authenticated cookies file exists."
    elif cookie_count > 0 and auth_cookie_names:
        result["message"] = f"{label} cookies file does not contain authenticated login cookies."
    else:
        result["message"] = f"{label} cookies file has no matching cookies."
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


def _network_security_status(settings: Settings) -> dict:
    return {
        "ok": True,
        "fake_ip_trust_enabled": settings.fake_ip_trust_enabled,
        "fake_ip_cidrs": list(normalize_fake_ip_cidrs(settings.fake_ip_cidrs)),
        "default_fake_ip_cidrs": list(DEFAULT_FAKE_IP_CIDRS),
        "allow_local_urls": settings.allow_local_urls,
        "mode": "trusted_fake_ip" if settings.fake_ip_trust_enabled else "strict",
    }


def _network_security_update(settings: Settings, payload: dict) -> dict:
    enabled = payload.get("fake_ip_trust_enabled")
    if not isinstance(enabled, bool):
        raise EasySourceFlowError(
            "invalid_network_security_config",
            "Fake-IP trust must be enabled or disabled explicitly.",
            ["Use the Web toggle or send a JSON boolean."],
        )
    raw_cidrs = payload.get("fake_ip_cidrs", settings.fake_ip_cidrs)
    if not isinstance(raw_cidrs, (str, list, tuple)):
        raise EasySourceFlowError(
            "invalid_network_security_config",
            "Fake-IP ranges must be a comma-separated string or a list.",
            ["Enter one CIDR per line, such as 198.18.0.0/15."],
        )
    try:
        cidrs = normalize_fake_ip_cidrs(raw_cidrs)
    except ValueError as exc:
        raise EasySourceFlowError(
            "invalid_network_security_config",
            str(exc),
            ["Use non-global CIDR ranges and do not include loopback, link-local, or multicast networks."],
        ) from exc
    if enabled and not cidrs:
        raise EasySourceFlowError(
            "invalid_network_security_config",
            "At least one fake-IP CIDR is required when trusted mode is enabled.",
            ["Use 198.18.0.0/15 for common Surge and Clash fake-IP configurations."],
        )
    cidr_text = ",".join(cidrs)
    config_file = _write_env_values(
        _config_file_path(),
        {
            "EASYSOURCEFLOW_TRUST_FAKE_IP": "true" if enabled else "false",
            "EASYSOURCEFLOW_FAKE_IP_CIDRS": cidr_text,
        },
    )
    object.__setattr__(settings, "fake_ip_trust_enabled", enabled)
    object.__setattr__(settings, "fake_ip_cidrs", cidr_text)
    logger.info("network security configuration updated fake_ip_trust=%s cidr_count=%s", enabled, len(cidrs))
    result = _network_security_status(settings)
    result["config_file"] = str(config_file)
    return result


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
        "session_refresh_command": "/new",
        "session_refresh_message": "安装或更新 Skill 后，在目标 Agent 聊天中单独发送 /new，以加载新的会话规则。",
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
        service["id"]: model_service_is_configured(service, configured_values)
        for service in _MODEL_SERVICES
    }
    credential_status["local"] = True
    if settings.model_api_key:
        credential_status[active_service["id"]] = True
    if active_service.get("requires_api_key") is False:
        credential_status[active_service["id"]] = True
    fallback = settings.model_fallbacks[0] if settings.model_fallbacks else None
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
        "fallback_service_id": fallback.service_id if fallback else "",
        "fallback_model": fallback.model if fallback else "",
        "fallback_strong_model": fallback.strong_model if fallback else "",
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


def _model_test(settings: Settings, payload: dict | None = None) -> dict:
    payload = payload or {}
    requested_service_id = str(payload.get("service_id") or "").strip().lower()
    selected_service = _model_service_by_id(requested_service_id) if requested_service_id else _model_service_for_settings(settings)
    if selected_service is None:
        raise EasySourceFlowError(
            "invalid_model_config",
            "Unsupported model service.",
            ["Choose one of the model services returned by GET /model."],
        )
    configured_values = _read_env_values(_config_file_path())
    key_name = _MODEL_SERVICE_KEY_NAMES.get(selected_service["id"])
    api_key = str(payload.get("model_api_key") or "").strip()
    if not api_key and key_name:
        api_key = configured_values.get(key_name, "")
    if not api_key and selected_service["id"] == _model_service_for_settings(settings)["id"]:
        api_key = settings.model_api_key
    model = str(payload.get("model") or selected_service["default_model"])
    strong_model = str(payload.get("strong_model") or selected_service["strong_model"])
    _validate_service_models(selected_service, model, strong_model)
    candidate = replace(
        settings,
        model_provider=str(payload.get("provider") or selected_service["provider"]),
        model=model,
        strong_model=strong_model,
        deepseek_base_url=str(payload.get("model_base_url") or selected_service["base_url"]),
        deepseek_api_key=api_key,
    )
    model_check = run_model_check(candidate)
    return {
        "ok": bool(model_check.get("ok")),
        "check": model_check,
        "tested": {
            "service_id": selected_service["id"],
            "model": candidate.model,
            "strong_model": candidate.strong_model,
        },
        "model": _model_status(settings),
    }


def _model_catalog_status(settings: Settings, payload: dict | None = None) -> dict:
    payload = payload or {}
    service_id = str(payload.get("service_id") or "").strip().lower()
    service = _model_service_by_id(service_id)
    if service is None:
        raise EasySourceFlowError(
            "invalid_model_config",
            "Unsupported model service.",
            ["Choose one of the model services returned by GET /model."],
        )
    configured_values = _read_env_values(_config_file_path())
    key_name = _MODEL_SERVICE_KEY_NAMES.get(service_id)
    api_key = str(payload.get("model_api_key") or "").strip()
    if not api_key and key_name:
        api_key = configured_values.get(key_name, "")
    if not api_key and service_id == _model_service_for_settings(settings)["id"]:
        api_key = settings.model_api_key
    return model_catalog(
        service,
        api_key,
        settings.data_dir / "cache" / "model-catalog.json",
        force_refresh=bool(payload.get("force_refresh")),
    )


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
    if service is not None:
        _validate_service_models(service, model, strong_model)
    if provider != "local" and not model_base_url.startswith(("http://", "https://")):
        raise EasySourceFlowError("invalid_model_config", "Model base URL must start with http:// or https://.", ["Use an official API base URL or a compatible endpoint."])

    previous_service = _model_service_for_settings(settings)
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
        **model_profile_env_values(service_id, model, strong_model, model_base_url),
    }
    if key_name and (model_api_key or clear_model_api_key):
        values[key_name] = active_api_key
    previous_key_name = _MODEL_SERVICE_KEY_NAMES.get(previous_service["id"])
    if previous_key_name and settings.model_api_key and not configured_values.get(previous_key_name):
        values[previous_key_name] = settings.model_api_key
    merged_values = {**configured_values, **values}
    preferred_fallback = str(configured_values.get(MODEL_FALLBACK_SERVICE_KEY, "")).strip().lower()
    if previous_service["id"] != service_id and model_service_is_configured(previous_service, merged_values):
        preferred_fallback = previous_service["id"]
    merged_values[MODEL_FALLBACK_SERVICE_KEY] = preferred_fallback
    fallback_profiles = configured_model_profiles(merged_values, service_id)
    values[MODEL_FALLBACK_SERVICE_KEY] = fallback_profiles[0].service_id if fallback_profiles else ""
    config_file = _write_env_values(_config_file_path(), values)
    object.__setattr__(settings, "model_provider", provider)
    object.__setattr__(settings, "model", model)
    object.__setattr__(settings, "strong_model", strong_model)
    object.__setattr__(settings, "deepseek_base_url", model_base_url)
    object.__setattr__(settings, "deepseek_api_key", active_api_key)
    _refresh_model_fallbacks(settings, {**configured_values, **values})
    logger.info("model configuration updated service=%s provider=%s model=%s strong_model=%s config_file=%s", service_id, provider, model, strong_model, config_file)
    return {"ok": True, "config_file": str(config_file), "model": _model_status(settings)}


def _model_credential_update(settings: Settings, payload: dict, delete: bool = False) -> dict:
    service_id = str(payload.get("service_id") or "").strip().lower()
    service = _model_service_by_id(service_id)
    if service is None or service_id == "local":
        raise EasySourceFlowError(
            "invalid_model_credential",
            "Choose a model service that supports API credentials.",
            ["Choose one of the external model services returned by GET /model."],
        )
    api_key = str(payload.get("model_api_key") or "").strip()
    if not delete and not api_key:
        raise EasySourceFlowError(
            "invalid_model_credential",
            "API Key cannot be empty.",
            ["Enter the API Key issued by the selected model service."],
        )

    key_name = _MODEL_SERVICE_KEY_NAMES[service_id]
    value = "" if delete else api_key
    values = {key_name: value, **model_profile_enabled_env_values(service_id, not delete)}
    configured_values = _read_env_values(_config_file_path())
    active_service_id = _model_service_for_settings(settings)["id"]
    if service_id == active_service_id:
        values.update(
            {
                "EASYSOURCEFLOW_MODEL_API_KEY": value,
                "DEEPSEEK_API_KEY": value,
            }
        )
        object.__setattr__(settings, "deepseek_api_key", value)
    merged_values = {**configured_values, **values}
    active_service_id = _model_service_for_settings(settings)["id"]
    fallback_profiles = configured_model_profiles(merged_values, active_service_id)
    values[MODEL_FALLBACK_SERVICE_KEY] = fallback_profiles[0].service_id if fallback_profiles else ""
    config_file = _write_env_values(_config_file_path(), values)
    _refresh_model_fallbacks(settings, {**configured_values, **values})
    logger.info(
        "model credential %s service=%s config_file=%s",
        "deleted" if delete else "updated",
        service_id,
        config_file,
    )
    return {"ok": True, "config_file": str(config_file), "model": _model_status(settings)}


def _model_service_by_id(service_id: str) -> dict | None:
    return model_service_by_id(service_id)


def _validate_service_models(service: dict, model: str, strong_model: str) -> None:
    for name in (model, strong_model):
        owner = next(
            (
                candidate
                for candidate in _MODEL_SERVICES
                if candidate["id"] != service["id"]
                and name in [*candidate["models"], *candidate.get("legacy_models", [])]
            ),
            None,
        )
        if owner is not None:
            raise EasySourceFlowError(
                "invalid_model_config",
                f"Model {name} belongs to {owner['label']}, not {service['label']}.",
                [f"Choose a {service['label']} model or enter a custom model ID for that service."],
            )


def _model_service_for_config(provider: str, base_url: str) -> dict:
    return model_service_for_config(provider, base_url)


def _model_service_for_settings(settings: Settings) -> dict:
    return _model_service_for_config(settings.model_provider, settings.model_base_url)


def _refresh_model_fallbacks(settings: Settings, configured_values: dict[str, str]) -> None:
    active_service_id = _model_service_for_settings(settings)["id"]
    profiles = configured_model_profiles(configured_values, active_service_id)
    object.__setattr__(settings, "model_fallbacks", profiles[:1])


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
    opened = _open_login_url(url)
    return {
        "ok": bool(opened),
        "url": url,
        "message": "Opened the Bilibili login page. Login state will be imported automatically after sign-in.",
    }


def _open_youtube_login() -> dict:
    url = "https://www.youtube.com/"
    opened = _open_login_url(url)
    return {
        "ok": bool(opened),
        "url": url,
        "message": "Opened YouTube. Login state will be connected automatically after sign-in.",
    }


def _open_login_url(url: str) -> bool:
    configured_chrome = os.environ.get("EASYSOURCEFLOW_CHROME_PATH", "").strip()
    if configured_chrome and Path(configured_chrome).expanduser().is_file():
        try:
            subprocess.Popen(
                [str(Path(configured_chrome).expanduser()), url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except OSError:
            logger.warning("configured Chrome could not open login page", exc_info=True)
    if sys.platform == "darwin" and Path("/Applications/Google Chrome.app").exists():
        try:
            subprocess.Popen(
                ["open", "-a", "Google Chrome", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except OSError:
            logger.warning("Google Chrome could not open login page", exc_info=True)
    return bool(webbrowser.open(url, new=2))


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
        required_auth_cookie_names=_BILIBILI_AUTH_COOKIE_NAMES,
    )
    config_file = _write_env_values(
        _config_file_path(),
        {"EASYSOURCEFLOW_BILIBILI_COOKIES_FILE": str(cookies_path)},
    )
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
        required_auth_cookie_names=_YOUTUBE_AUTH_COOKIE_NAMES,
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
    logger.info(
        "youtube browser login configured source=%s snapshot=%s config_file=%s",
        browser_cookie_source,
        cookies_path,
        config_file,
    )
    return {"ok": True, "config_file": str(config_file), "cookies": _youtube_cookie_status(settings)}


def _disconnect_bilibili_login(settings: Settings) -> dict:
    removed = _remove_managed_cookie_files(
        settings.bilibili_cookies_file,
        default_bilibili_cookies_file(settings),
        settings.data_dir,
    )
    config_file = _write_env_values(
        _config_file_path(),
        {"EASYSOURCEFLOW_BILIBILI_COOKIES_FILE": ""},
    )
    object.__setattr__(settings, "bilibili_cookies_file", "")
    logger.info("bilibili login disconnected config_file=%s", config_file)
    return {
        "ok": True,
        "message": "Bilibili login was disconnected from EasySourceFlow. Chrome remains signed in.",
        "cookie_file_removed": removed,
        "cookies": _bilibili_cookie_status(settings),
    }


def _disconnect_youtube_login(settings: Settings) -> dict:
    removed = _remove_managed_cookie_files(
        settings.youtube_cookies_file,
        default_youtube_cookies_file(settings),
        settings.data_dir,
    )
    config_file = _write_env_values(
        _config_file_path(),
        {
            "EASYSOURCEFLOW_YOUTUBE_COOKIES_FILE": "",
            "EASYSOURCEFLOW_YOUTUBE_BROWSER_COOKIE_SOURCE": "",
        },
    )
    object.__setattr__(settings, "youtube_cookies_file", "")
    object.__setattr__(settings, "youtube_browser_cookie_source", "")
    logger.info("youtube login disconnected config_file=%s", config_file)
    return {
        "ok": True,
        "message": "YouTube login was disconnected from EasySourceFlow. Chrome remains signed in.",
        "cookie_file_removed": removed,
        "cookies": _youtube_cookie_status(settings),
    }


def _remove_managed_cookie_files(configured_path: str, default_path: Path, data_dir: Path) -> bool:
    managed_roots = [data_dir.expanduser().resolve()]
    if data_dir.parent.name == "launchd":
        managed_roots.append(data_dir.parent.parent.expanduser().resolve())
    candidates = {default_path.expanduser().resolve()}
    if configured_path:
        configured = Path(configured_path).expanduser().resolve()
        if any(configured.is_relative_to(root) for root in managed_roots):
            candidates.add(configured)
    removed = False
    for path in candidates:
        try:
            path.unlink()
            removed = True
        except FileNotFoundError:
            continue
    return removed


def _import_browser_cookies(
    settings: Settings,
    *,
    cookies_path: Path,
    platform: str,
    test_url: str,
    allowed_domains: set[str],
    error_code: str,
    browser_cookie_source: str = "chrome",
    required_auth_cookie_names: set[str] | None = None,
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
        cookie_count = _filter_cookie_file(raw_path, filtered_path, allowed_domains)
        if cookie_count > 0:
            if required_auth_cookie_names:
                _, cookie_names = _cookie_file_summary(filtered_path, allowed_domains)
                if not cookie_names.intersection(required_auth_cookie_names):
                    raise _login_not_ready_error(platform)
            filtered_path.replace(cookies_path)
        elif completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip().splitlines()[-1:]
            message = detail[0] if detail else f"Could not import {platform} cookies from Chrome."
            if required_auth_cookie_names and _is_login_pending_error(message):
                raise _login_not_ready_error(platform)
            raise EasySourceFlowError(
                error_code,
                message,
                [
                    f"Open Chrome and confirm the {platform} account is signed in.",
                    "Close private browsing windows and retry.",
                    "If Chrome cookies are locked, export a Netscape cookies file manually.",
                ],
            )
        else:
            if required_auth_cookie_names:
                raise _login_not_ready_error(platform)
            raise EasySourceFlowError(
                error_code,
                f"Chrome did not provide any {platform} cookies.",
                [f"Open {platform} in Chrome, sign in, and retry the import."],
            )
    try:
        cookies_path.chmod(0o600)
    except OSError:
        logger.debug("could not chmod cookies file platform=%s", platform, exc_info=True)


def _is_login_pending_error(message: str) -> bool:
    lowered = message.lower()
    return any(
        marker in lowered
        for marker in (
            "sign in to confirm",
            "login required",
            "authentication required",
            "use --cookies",
            "请先登录",
        )
    )


def _login_not_ready_error(platform: str) -> EasySourceFlowError:
    return EasySourceFlowError(
        f"{platform.lower()}_login_not_ready",
        f"{platform} login has not been detected yet.",
        [f"Complete the {platform} login in Chrome; EasySourceFlow will keep checking automatically."],
    )


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
    with _CONFIG_FILE_LOCK:
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
