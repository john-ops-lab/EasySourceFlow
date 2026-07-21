"""Application service layer."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

from .config import Settings
from .cleanup import cleanup_artifacts
from .documents import document_payload_to_text
from .errors import EasySourceFlowError
from .extractors.video import extract_video_document
from .extractors.web import extract_web_document
from .extractors.wechat import extract_wechat_document
from .health import run_health_checks
from .media_download import download_media, media_download_root
from .models import SourceDocument
from .notifications import notify_event
from .output import write_resource_package, write_summary_markdown
from .store import JobStore
from .digest import digest_with_provider
from .url_utils import detect_source_type, normalize_url


logger = logging.getLogger(__name__)
SUMMARY_PIPELINE_VERSION = "2026-07-16-v3"


class EasySourceFlowService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = JobStore(settings.database_path)
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="easysourceflow")
        recovered = self.store.prepare_recoverable_jobs()
        for job in recovered:
            self._resume_job(job)
        if recovered:
            logger.warning("requeued interrupted jobs count=%s", len(recovered))

    def submit_link(
        self,
        url: str,
        instruction: str = "",
        run_async: bool = False,
        summary_quality: str = "fast",
        force_refresh: bool = False,
    ) -> dict:
        summary_quality = _normalize_summary_quality(summary_quality)
        job_id = f"job_{uuid.uuid4().hex}"
        self.store.create_job(
            job_id,
            url,
            instruction,
            request_kind="link",
            summary_quality=summary_quality,
            request_payload={"url": url},
            force_refresh=force_refresh,
        )
        if run_async:
            self.executor.submit(self._run_job, job_id, url, instruction, summary_quality, force_refresh)
            job = self.store.get_job(job_id)
            return _require_job(job, job_id)
        self._run_job(job_id, url, instruction, summary_quality, force_refresh)
        job = self.store.get_job(job_id)
        return _require_job(job, job_id)

    def summarize_link(self, url: str, instruction: str = "", summary_quality: str = "fast", force_refresh: bool = False) -> dict:
        return self.submit_link(url, instruction, summary_quality=summary_quality, force_refresh=force_refresh)

    def submit_link_async(
        self,
        url: str,
        instruction: str = "",
        summary_quality: str = "fast",
        force_refresh: bool = False,
    ) -> dict:
        return self.submit_link(url, instruction, run_async=True, summary_quality=summary_quality, force_refresh=force_refresh)

    def submit_text_document(
        self,
        title: str,
        content: str,
        instruction: str = "",
        run_async: bool = False,
        metadata: Optional[dict] = None,
        summary_quality: str = "fast",
        force_refresh: bool = False,
    ) -> dict:
        summary_quality = _normalize_summary_quality(summary_quality)
        job_id = f"job_{uuid.uuid4().hex}"
        safe_title = (title or "local-document").strip()[:180] or "local-document"
        doc_metadata = dict(metadata or {"input_kind": "uploaded_text"})
        source_url, source_type, extraction_method = _document_source_info(doc_metadata, safe_title)
        if source_type != "local_file":
            doc_metadata.update(
                {
                    "source_url": source_url,
                    "source_type": source_type,
                    "extraction_method": extraction_method,
                }
            )
        request_payload = {"title": safe_title, "content": content, "metadata": doc_metadata}
        self.store.create_job(
            job_id,
            source_url,
            instruction,
            request_kind="document",
            summary_quality=summary_quality,
            request_payload=request_payload,
            force_refresh=force_refresh,
        )
        if run_async:
            self.executor.submit(
                self._run_text_job,
                job_id,
                safe_title,
                content,
                instruction,
                doc_metadata,
                summary_quality,
                force_refresh,
            )
            job = self.store.get_job(job_id)
            return _require_job(job, job_id)
        self._run_text_job(job_id, safe_title, content, instruction, doc_metadata, summary_quality, force_refresh)
        job = self.store.get_job(job_id)
        return _require_job(job, job_id)

    def submit_document_payload(self, payload: dict, run_async: bool = True) -> dict:
        title, content, metadata = document_payload_to_text(payload)
        source_url = str(payload.get("source_url") or "").strip()
        if source_url:
            metadata = {**metadata, "source_url": source_url}
        instruction = str(payload.get("instruction", ""))
        summary_quality = str(payload.get("summary_quality") or "fast")
        return self.submit_text_document(
            title=title,
            content=content,
            instruction=instruction,
            run_async=run_async,
            metadata=metadata,
            summary_quality=summary_quality,
            force_refresh=bool(payload.get("force_refresh", False)),
        )

    def retry_job(
        self,
        job_id: str,
        instruction: Optional[str] = None,
        summary_quality: Optional[str] = None,
        force_refresh: bool = True,
    ) -> Optional[dict]:
        original = self.get_job(job_id)
        if not original or original.get("request_kind") == "media_download":
            return None
        retry_instruction = original.get("instruction") if instruction is None else instruction
        result = original.get("result") or {}
        retry_quality = _normalize_summary_quality(summary_quality or original.get("summary_quality") or result.get("summary_quality") or "fast")
        source = result.get("source") or {}
        request_payload = original.get("request_payload") or {}
        if original.get("request_kind") == "document" and request_payload.get("content"):
            return self.submit_text_document(
                title=request_payload.get("title") or original.get("title") or original["url"],
                content=str(request_payload["content"]),
                instruction=retry_instruction or "",
                run_async=True,
                metadata=request_payload.get("metadata") or {"input_kind": "retried_document"},
                summary_quality=retry_quality,
                force_refresh=force_refresh,
            )
        if original.get("url", "").startswith("local://") and source.get("content_text"):
            return self.submit_text_document(
                title=source.get("title") or original.get("title") or original["url"],
                content=source["content_text"],
                instruction=retry_instruction or "",
                run_async=True,
                summary_quality=retry_quality,
                force_refresh=force_refresh,
            )
        return self.submit_link_async(
            url=original["url"],
            instruction=retry_instruction or "",
            summary_quality=retry_quality,
            force_refresh=force_refresh,
        )

    def submit_batch_async(
        self,
        urls: list[str],
        instruction: str = "",
        summary_quality: str = "fast",
        force_refresh: bool = False,
    ) -> dict:
        summary_quality = _normalize_summary_quality(summary_quality)
        batch_id = f"batch_{uuid.uuid4().hex}"
        job_ids = []
        for url in urls:
            job = self.submit_link_async(
                url=url,
                instruction=instruction,
                summary_quality=summary_quality,
                force_refresh=force_refresh,
            )
            job_ids.append(job["job_id"])
        logger.info("submitted batch batch_id=%s count=%s", batch_id, len(job_ids))
        return self.store.create_batch(batch_id, instruction, job_ids)

    def get_job(self, job_id: str) -> Optional[dict]:
        return self.store.get_job(job_id)

    def get_batch(self, batch_id: str) -> Optional[dict]:
        return self.store.get_batch(batch_id)

    def list_batches(self, limit: int = 20) -> list:
        return self.store.list_batches(limit=limit)

    def list_jobs(self, limit: int = 20, status: Optional[str] = None) -> list:
        return self.store.list_jobs(limit=limit, status=status, exclude_request_kind="media_download")

    def submit_media_download_async(self, url: str, media_type: str, format_name: str) -> dict:
        job_id = f"download_{uuid.uuid4().hex}"
        payload = {
            "url": str(url or "").strip(),
            "media_type": str(media_type or "").strip().lower(),
            "format": str(format_name or "").strip().lower(),
        }
        self.store.create_job(
            job_id,
            payload["url"],
            "",
            request_kind="media_download",
            request_payload=payload,
        )
        self.executor.submit(
            self._run_media_download_job,
            job_id,
            payload["url"],
            payload["media_type"],
            payload["format"],
        )
        return _require_job(self.store.get_job(job_id), job_id)

    def list_media_downloads(self, limit: int = 20, status: Optional[str] = None) -> list:
        return self.store.list_jobs(limit=limit, status=status, request_kind="media_download")

    def retry_media_download(self, job_id: str) -> Optional[dict]:
        original = self.get_job(job_id)
        if not original or original.get("request_kind") != "media_download":
            return None
        request_payload = original.get("request_payload") or {}
        return self.submit_media_download_async(
            url=str(request_payload.get("url") or original.get("url") or ""),
            media_type=str(request_payload.get("media_type") or "video"),
            format_name=str(request_payload.get("format") or "1080p"),
        )

    def media_download_queue_status(self) -> dict:
        return {"counts": self.store.status_counts(request_kind="media_download")}

    def media_download_file(self, job_id: str) -> Optional[Path]:
        job = self.store.get_job(job_id)
        if not job or job.get("request_kind") != "media_download" or job.get("status") != "succeeded":
            return None
        file_value = str((job.get("result") or {}).get("file_path") or "")
        if not file_value:
            return None
        root = media_download_root(self.settings)
        try:
            path = Path(file_value).expanduser().resolve()
            path.relative_to(root)
        except (OSError, ValueError):
            logger.warning("rejected media download path outside root job_id=%s", job_id)
            return None
        return path if path.is_file() else None

    def search_outputs(self, query: str, source_type: str = "", limit: int = 50) -> dict:
        return self.store.search_outputs(self.settings.output_dir, query, source_type=source_type, limit=limit)

    def cancel_job(self, job_id: str) -> Optional[dict]:
        job = self.store.get_job(job_id)
        if not job or job.get("request_kind") == "media_download":
            return None
        return self._cancel_job(job, notify=True)

    def cancel_media_download(self, job_id: str) -> Optional[dict]:
        job = self.store.get_job(job_id)
        if not job or job.get("request_kind") != "media_download":
            return None
        return self._cancel_job(job, notify=False)

    def _cancel_job(self, job: dict, notify: bool) -> dict:
        job_id = job["job_id"]
        if job["status"] in {"succeeded", "failed", "canceled"}:
            return job
        self.store.mark_canceled(job_id)
        logger.info("job canceled job_id=%s previous_status=%s", job_id, job["status"])
        canceled = self.store.get_job(job_id)
        if canceled and notify:
            self._notify_job(canceled)
        return _require_job(canceled, job_id)

    def queue_status(self) -> dict:
        counts = self.store.status_counts(exclude_request_kind="media_download")
        active_limit = 100
        active = self.store.list_jobs(limit=active_limit, status="running", exclude_request_kind="media_download") + self.store.list_jobs(limit=active_limit, status="queued", exclude_request_kind="media_download")
        expected_active = int(counts.get("running", 0)) + int(counts.get("queued", 0))
        return {
            "counts": counts,
            "active": active[:active_limit],
            "active_count": expected_active,
            "active_returned": min(len(active), active_limit),
            "active_limited": expected_active > active_limit,
        }

    def health(self) -> dict:
        return run_health_checks(self.settings)

    def cleanup(
        self,
        days: int = 14,
        dry_run: bool = True,
        include_temp: bool = True,
        include_outputs: bool = True,
        include_jobs: bool = False,
    ) -> dict:
        return cleanup_artifacts(
            self.settings,
            days=days,
            dry_run=dry_run,
            include_temp=include_temp,
            include_outputs=include_outputs,
            include_jobs=include_jobs,
        )

    def _run_job(self, job_id: str, url: str, instruction: str, summary_quality: str, force_refresh: bool = False) -> None:
        try:
            if self.store.is_canceled(job_id):
                return
            logger.info("job started job_id=%s kind=link", job_id)
            self.store.mark_running(job_id, "extracting", 0.25)
            canonical_url = normalize_url(
                url,
                self.settings.allow_local_urls,
                self.settings.trusted_fake_ip_cidrs,
            )
            source_type = detect_source_type(canonical_url)
            if source_type in {"bilibili", "youtube"}:
                summary_quality = "pro"
            cache_context = _cache_context(self.settings, summary_quality)
            cached = None if force_refresh else self.store.get_cached_result(
                canonical_url,
                instruction,
                summary_quality,
                cache_context=cache_context,
                max_age_seconds=self.settings.cache_ttl_seconds,
            )
            if cached:
                self.store.mark_succeeded_from_cache(job_id, cached)
                completed = self.store.get_job(job_id)
                if completed:
                    self._notify_job(completed)
                return

            progress = lambda stage, progress: self.store.mark_running(job_id, stage, progress)
            if source_type in {"bilibili", "youtube"}:
                document = extract_video_document(
                    url,
                    self.settings,
                    progress_callback=progress,
                )
            elif source_type == "wechat":
                document = extract_wechat_document(url, self.settings)
            else:
                document = extract_web_document(url, self.settings)
            if self.store.is_canceled(job_id):
                logger.info("job stopped because it was canceled job_id=%s", job_id)
                return
            self._finish_document_job(
                job_id,
                document,
                instruction,
                use_cache=True,
                summary_quality=summary_quality,
                cache_context=cache_context,
            )
        except EasySourceFlowError as exc:
            logger.warning("job failed with expected error job_id=%s code=%s", job_id, exc.code)
            self.store.mark_failed(job_id, exc.code, exc.message, exc.next_steps)
            failed = self.store.get_job(job_id)
            if failed:
                self._notify_job(failed)
        except Exception as exc:
            logger.exception("job failed unexpectedly job_id=%s", job_id)
            self.store.mark_failed(job_id, "unexpected_error", f"Unexpected error: {type(exc).__name__}.")
            failed = self.store.get_job(job_id)
            if failed:
                self._notify_job(failed)

    def _run_text_job(
        self,
        job_id: str,
        title: str,
        content: str,
        instruction: str,
        metadata: dict,
        summary_quality: str,
        force_refresh: bool = False,
    ) -> None:
        try:
            if self.store.is_canceled(job_id):
                return
            logger.info("job started job_id=%s kind=document", job_id)
            self.store.mark_running(job_id, "extracting", 0.25)
            text = (content or "").strip()
            if len(text) < 20:
                self.store.mark_failed(
                    job_id,
                    "invalid_document",
                    "Local document content is too short to summarize.",
                    ["Choose a text, Markdown, subtitle, or transcript file with readable content."],
                )
                failed = self.store.get_job(job_id)
                if failed:
                    self._notify_job(failed)
                return
            if len(text) > self.settings.max_content_chars:
                text = text[: self.settings.max_content_chars].rsplit("\n", 1)[0]
            source_url, source_type, extraction_method = _document_source_info(metadata, title)
            digest_input = f"{title}\0{text}"
            if source_type != "local_file":
                digest_input += f"\0{source_type}\0{source_url}"
            content_digest = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()
            cache_canonical_url = f"local://document/{content_digest}"
            cache_context = _cache_context(self.settings, summary_quality)
            cached = None if force_refresh else self.store.get_cached_result(
                cache_canonical_url,
                instruction,
                summary_quality,
                cache_context=cache_context,
                max_age_seconds=self.settings.cache_ttl_seconds,
            )
            if cached:
                self.store.mark_succeeded_from_cache(job_id, cached, canonical_url=source_url)
                completed = self.store.get_job(job_id)
                if completed:
                    self._notify_job(completed)
                return
            document = SourceDocument(
                source_url=source_url,
                canonical_url=source_url,
                source_type=source_type,
                title=title,
                author=None,
                published_at=None,
                language=None,
                content_text=text,
                content_markdown=text,
                metadata=metadata,
                extraction_method=extraction_method,
            )
            if self.store.is_canceled(job_id):
                logger.info("job stopped because it was canceled job_id=%s", job_id)
                return
            self._finish_document_job(
                job_id,
                document,
                instruction,
                use_cache=True,
                summary_quality=summary_quality,
                cache_context=cache_context,
                cache_canonical_url=cache_canonical_url,
            )
        except EasySourceFlowError as exc:
            logger.warning("document job failed with expected error job_id=%s code=%s", job_id, exc.code)
            self.store.mark_failed(job_id, exc.code, exc.message, exc.next_steps)
            failed = self.store.get_job(job_id)
            if failed:
                self._notify_job(failed)
        except Exception as exc:
            logger.exception("document job failed unexpectedly job_id=%s", job_id)
            self.store.mark_failed(job_id, "unexpected_error", f"Unexpected error: {type(exc).__name__}.")
            failed = self.store.get_job(job_id)
            if failed:
                self._notify_job(failed)

    def _run_media_download_job(self, job_id: str, url: str, media_type: str, format_name: str) -> None:
        destination = media_download_root(self.settings) / job_id
        try:
            if self.store.is_canceled(job_id):
                return
            self.store.mark_running(job_id, "preparing_download", 0.02)
            result = download_media(
                url,
                media_type,
                format_name,
                self.settings,
                destination,
                progress_callback=lambda stage, progress: self.store.mark_running(job_id, stage, progress),
                cancel_check=lambda: self.store.is_canceled(job_id),
            )
            if result.get("canceled") or self.store.is_canceled(job_id):
                return
            result["download_url"] = f"/downloads/{job_id}/file"
            self.store.mark_succeeded(
                job_id,
                str(result.get("canonical_url") or url),
                str(result.get("title") or result.get("file_name") or url),
                result,
            )
        except EasySourceFlowError as exc:
            shutil.rmtree(destination, ignore_errors=True)
            logger.warning("media download failed job_id=%s code=%s", job_id, exc.code)
            self.store.mark_failed(job_id, exc.code, exc.message, exc.next_steps)
        except Exception as exc:
            shutil.rmtree(destination, ignore_errors=True)
            logger.exception("media download failed unexpectedly job_id=%s", job_id)
            self.store.mark_failed(job_id, "unexpected_error", f"Unexpected error: {type(exc).__name__}.")

    def _finish_document_job(
        self,
        job_id: str,
        document: SourceDocument,
        instruction: str,
        use_cache: bool,
        summary_quality: str = "fast",
        cache_context: str = "",
        cache_canonical_url: str = "",
    ) -> None:
        if self.store.is_canceled(job_id):
            return
        self.store.mark_running(job_id, "summarizing", 0.75)
        summary_quality = _normalize_summary_quality(summary_quality)
        summary_settings = _summary_settings(self.settings, summary_quality)
        metadata = dict(document.metadata or {})
        metadata["summary_quality"] = summary_quality
        metadata["summary_model"] = summary_settings.model
        document = replace(document, metadata=metadata)
        fallback_settings = _fallback_summary_settings(self.settings, summary_quality)
        logger.info(
            "job summarizing job_id=%s summary_quality=%s model=%s fallback_model=%s",
            job_id,
            summary_quality,
            summary_settings.model,
            fallback_settings[0].model if fallback_settings else "",
        )
        if fallback_settings:
            result = digest_with_provider(summary_settings, document, instruction, fallback_settings)
        else:
            result = digest_with_provider(summary_settings, document, instruction)
        if self.store.is_canceled(job_id):
            logger.info("job stopped after summarization because it was canceled job_id=%s", job_id)
            return
        self.store.mark_running(job_id, "writing_output", 0.90)
        output_path = write_summary_markdown(result, self.settings.output_dir)
        package_path = write_resource_package(result, output_path)
        self.store.index_output(self.settings.output_dir, output_path)
        result_payload = result.to_dict()
        result_payload["cache_hit"] = False
        result_payload["summary_quality"] = summary_quality
        result_payload["summary_model"] = str(result.source.metadata.get("summary_model") or summary_settings.model)
        result_payload["model_failover_used"] = bool(result.source.metadata.get("model_failover_used"))
        result_payload["output_markdown_path"] = str(output_path)
        if package_path:
            result_payload["resource_package_path"] = str(package_path)
        self.store.mark_succeeded(
            job_id=job_id,
            canonical_url=document.canonical_url,
            title=result.title,
            result=result_payload,
        )
        logger.info("job succeeded job_id=%s output_path=%s", job_id, output_path)
        if use_cache:
            self.store.put_cached_result(
                cache_canonical_url or document.canonical_url,
                instruction,
                result.title,
                result_payload,
                summary_quality,
                cache_context=cache_context,
            )
        completed = self.store.get_job(job_id)
        if completed:
            self._notify_job(completed)

    def _resume_job(self, job: dict) -> None:
        job_id = str(job.get("job_id") or "")
        request_kind = str(job.get("request_kind") or "link")
        payload = job.get("request_payload") or {}
        instruction = str(job.get("instruction") or "")
        summary_quality = _normalize_summary_quality(job.get("summary_quality") or "fast")
        force_refresh = bool(job.get("force_refresh"))
        if request_kind == "link":
            url = str(payload.get("url") or job.get("url") or "")
            if url and not url.startswith("local://"):
                self.executor.submit(self._run_job, job_id, url, instruction, summary_quality, force_refresh)
                return
        elif request_kind == "document":
            content = str(payload.get("content") or "")
            if content:
                self.executor.submit(
                    self._run_text_job,
                    job_id,
                    str(payload.get("title") or job.get("title") or "local-document"),
                    content,
                    instruction,
                    payload.get("metadata") or {"input_kind": "recovered_document"},
                    summary_quality,
                    force_refresh,
                )
                return
        elif request_kind == "media_download":
            url = str(payload.get("url") or job.get("url") or "")
            if url:
                self.executor.submit(
                    self._run_media_download_job,
                    job_id,
                    url,
                    str(payload.get("media_type") or "video"),
                    str(payload.get("format") or "1080p"),
                )
                return
        self.store.mark_interrupted(job_id, "EasySourceFlow restarted but this job did not contain recoverable input.")
        failed = self.store.get_job(job_id)
        if failed:
            self._notify_job(failed)

    def _notify_job(self, job: dict) -> None:
        result = job.get("result") or {}
        event = f"job.{job.get('status') or 'unknown'}"
        notify_event(
            self.settings,
            event,
            {
                "job_id": job.get("job_id"),
                "status": job.get("status"),
                "title": job.get("title"),
                "error_code": job.get("error_code"),
                "error_message": job.get("error_message"),
                "output_markdown_path": result.get("output_markdown_path"),
                "resource_package_path": result.get("resource_package_path"),
            },
        )


def _document_source_info(metadata: dict, title: str) -> tuple[str, str, str]:
    raw_url = str((metadata or {}).get("source_url") or "").strip()
    if not raw_url:
        return f"local://{title}", "local_file", "local_text_upload"
    if len(raw_url) > 2048 or any(character.isspace() or ord(character) < 32 for character in raw_url):
        raise EasySourceFlowError(
            code="invalid_document_source",
            message="The cloud document source URL is invalid.",
            next_steps=["Provide the original HTTPS document link without spaces or control characters."],
        )
    parsed = urlsplit(raw_url)
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise EasySourceFlowError(
            code="invalid_document_source",
            message="Cloud document sources must use a normal HTTPS URL.",
            next_steps=["Provide the original HTTPS document link returned by the document connector."],
        )
    host = parsed.hostname.lower()
    try:
        port = parsed.port
    except ValueError as exc:
        raise EasySourceFlowError(
            code="invalid_document_source",
            message="The cloud document source URL has an invalid port.",
            next_steps=["Provide the original HTTPS document link returned by the document connector."],
        ) from exc
    netloc = host
    if port:
        netloc = f"{host}:{port}"
    source_url = urlunsplit(("https", netloc, parsed.path or "/", parsed.query, parsed.fragment))
    is_feishu = host == "feishu.cn" or host.endswith(".feishu.cn") or host == "larksuite.com" or host.endswith(".larksuite.com")
    if is_feishu:
        return source_url, "feishu_document", "agent_feishu_connector"
    return source_url, "cloud_document", "agent_document_connector"


def _require_job(job: Optional[dict], job_id: str) -> dict:
    if job is None:
        logger.error("job disappeared after creation job_id=%s", job_id)
        raise RuntimeError(f"Job {job_id} was not found after creation.")
    return job


def _normalize_summary_quality(value: str) -> str:
    return "pro" if str(value).strip().lower() in {"pro", "deep", "strong", "depth"} else "fast"


def _summary_settings(settings: Settings, summary_quality: str) -> Settings:
    if _normalize_summary_quality(summary_quality) == "pro":
        return replace(settings, model=settings.strong_model)
    return settings


def _fallback_summary_settings(settings: Settings, summary_quality: str) -> tuple[Settings, ...]:
    use_strong_model = _normalize_summary_quality(summary_quality) == "pro"
    candidates = []
    for profile in settings.model_fallbacks[:1]:
        candidates.append(
            replace(
                settings,
                model_provider=profile.provider,
                model=profile.strong_model if use_strong_model else profile.model,
                strong_model=profile.strong_model,
                deepseek_api_key=profile.api_key,
                deepseek_base_url=profile.base_url,
                model_fallbacks=(),
            )
        )
    return tuple(candidates)


def _cache_context(settings: Settings, summary_quality: str) -> str:
    summary_settings = _summary_settings(settings, summary_quality)
    fallback_settings = _fallback_summary_settings(settings, summary_quality)
    payload = {
        "provider": summary_settings.model_provider,
        "model": summary_settings.model,
        "base_url": summary_settings.model_base_url.rstrip("/"),
        "summary_prompt": hashlib.sha256(summary_settings.summary_prompt.encode("utf-8")).hexdigest()[:16],
        "summary_pipeline": SUMMARY_PIPELINE_VERSION,
        "fallback_models": [
            {
                "provider": candidate.model_provider,
                "model": candidate.model,
                "base_url": candidate.model_base_url.rstrip("/"),
            }
            for candidate in fallback_settings
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:20]
