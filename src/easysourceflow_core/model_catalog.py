"""Discover provider model IDs without making the Web UI depend on static lists."""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


logger = logging.getLogger(__name__)

_CACHE_VERSION = 1
_CACHE_TTL_SECONDS = 24 * 60 * 60
_CACHE_LOCK = threading.Lock()
_NON_SUMMARY_MODEL = re.compile(
    r"(?:^|[/_.-])(embedding|embed|rerank|moderation|whisper|tts|speech|audio|"
    r"image|video|music|dall-e|realtime|transcri(?:be|ption))(?:$|[/_.-])",
    re.IGNORECASE,
)


def model_catalog(
    service: dict,
    api_key: str,
    cache_path: Path,
    *,
    force_refresh: bool = False,
    timeout: float = 12,
    now: float | None = None,
) -> dict:
    """Return provider models, using a bounded cache and static models as fallback."""
    now = time.time() if now is None else now
    fallback_models = _model_records(service.get("models", []), source="built_in")
    cached = _cached_service(cache_path, str(service.get("id") or ""))
    cached_models = cached.get("models", []) if isinstance(cached, dict) else []
    cached_at = float(cached.get("updated_at") or 0) if isinstance(cached, dict) else 0
    cached_fresh = bool(cached_models and now - cached_at < _CACHE_TTL_SECONDS)

    discovery = service.get("model_discovery") or {}
    if service.get("requires_api_key", True) and not api_key:
        return _catalog_result(
            service,
            _merge_models(cached_models or fallback_models),
            status="key_required",
            message="填写 API Key 后，将自动获取当前账号最新可用的模型；当前型号仅供配置参考。",
            refreshed_at=cached_at or None,
        )

    if cached_fresh and not force_refresh:
        return _catalog_result(
            service,
            _merge_models(cached_models),
            status="cached",
            message="已使用最近同步的官方模型列表。",
            refreshed_at=cached_at,
        )

    if not discovery:
        return _catalog_result(
            service,
            _merge_models(cached_models or fallback_models),
            status="built_in",
            message="该服务商暂不支持自动读取模型，仍可手工输入模型 ID。",
            refreshed_at=cached_at or None,
        )
    try:
        discovered = _fetch_models(service, api_key, discovery, timeout)
        if not discovered:
            raise ValueError("provider returned no compatible text models")
        cache_entry = {"updated_at": now, "models": discovered}
        _write_cached_service(cache_path, str(service["id"]), cache_entry)
        return _catalog_result(
            service,
            _merge_models(discovered),
            status="live",
            message="已从服务商同步当前账号可用的模型。",
            refreshed_at=now,
        )
    except Exception as exc:
        logger.warning(
            "model catalog refresh failed service=%s error_type=%s",
            service.get("id"),
            type(exc).__name__,
        )
        return _catalog_result(
            service,
            _merge_models(cached_models or fallback_models),
            status="fallback",
            message=_discovery_error_message(exc, bool(cached_models)),
            refreshed_at=cached_at or None,
        )


def _fetch_models(service: dict, api_key: str, discovery: dict, timeout: float) -> list[dict]:
    style = str(discovery.get("style") or "openai").lower()
    endpoint = _discovery_endpoint(service, discovery, style)
    headers = {"accept": "application/json", "user-agent": "EasySourceFlow/model-catalog"}
    if api_key:
        if style == "gemini":
            headers["x-goog-api-key"] = api_key
        else:
            headers["authorization"] = "Bearer " + api_key
    request = Request(endpoint, headers=headers, method="GET")
    with urlopen(request, timeout=max(2, min(float(timeout), 20))) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if style == "gemini":
        return _parse_gemini_models(payload)
    if style == "ollama":
        return _parse_ollama_models(payload)
    return _parse_openai_models(payload)


def _discovery_endpoint(service: dict, discovery: dict, style: str) -> str:
    if discovery.get("url"):
        return str(discovery["url"])
    base_url = str(service.get("base_url") or "").rstrip("/")
    if style == "ollama" and base_url.endswith("/v1"):
        base_url = base_url[:-3]
    path = str(discovery.get("path") or ("/api/tags" if style == "ollama" else "/models"))
    return base_url + "/" + path.lstrip("/")


def _parse_openai_models(payload: object) -> list[dict]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return []
    records = []
    for item in payload["data"]:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or "").strip()
        if not _summary_model_id(model_id):
            continue
        record = {"id": model_id, "source": "provider"}
        for field in (
            "created",
            "owned_by",
            "context_length",
            "supports_image_in",
            "supports_video_in",
            "supports_reasoning",
        ):
            if field in item:
                record[field] = item[field]
        records.append(record)
    return _deduplicate_models(records)


def _parse_gemini_models(payload: object) -> list[dict]:
    if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
        return []
    records = []
    for item in payload["models"]:
        if not isinstance(item, dict):
            continue
        methods = item.get("supportedGenerationMethods") or item.get("supported_actions") or []
        if methods and "generateContent" not in methods:
            continue
        model_id = str(item.get("baseModelId") or item.get("name") or "").removeprefix("models/").strip()
        if not _summary_model_id(model_id):
            continue
        records.append(
            {
                "id": model_id,
                "source": "provider",
                "display_name": str(item.get("displayName") or model_id),
                "context_length": item.get("inputTokenLimit"),
            }
        )
    return _deduplicate_models(records)


def _parse_ollama_models(payload: object) -> list[dict]:
    if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
        return []
    records = []
    for item in payload["models"]:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("model") or item.get("name") or "").strip()
        if _summary_model_id(model_id):
            records.append({"id": model_id, "source": "provider"})
    return _deduplicate_models(records)


def _summary_model_id(model_id: str) -> bool:
    return bool(model_id and len(model_id) <= 200 and not _NON_SUMMARY_MODEL.search(model_id))


def _model_records(models: object, *, source: str) -> list[dict]:
    if not isinstance(models, list):
        return []
    return [{"id": item, "source": source} for item in models if isinstance(item, str) and item.strip()]


def _merge_models(*groups: object) -> list[dict]:
    records = []
    for group in groups:
        if isinstance(group, list):
            records.extend(item for item in group if isinstance(item, dict))
    return _deduplicate_models(records)


def _deduplicate_models(records: list[dict]) -> list[dict]:
    result = []
    seen = set()
    for record in records:
        model_id = str(record.get("id") or "").strip()
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        result.append({**record, "id": model_id})
    return result


def _catalog_result(
    service: dict,
    models: list[dict],
    *,
    status: str,
    message: str,
    refreshed_at: float | None,
) -> dict:
    built_in = set(service.get("models") or [])
    return {
        "ok": status in {"live", "cached", "built_in"},
        "service_id": service.get("id"),
        "status": status,
        "message": message,
        "refreshed_at": refreshed_at,
        "models": models,
        "model_ids": [item["id"] for item in models],
        "additional_model_ids": [
            item["id"]
            for item in models
            if item.get("source") == "provider" and item["id"] not in built_in
        ],
    }


def _cached_service(cache_path: Path, service_id: str) -> dict:
    with _CACHE_LOCK:
        payload = _read_cache(cache_path)
    services = payload.get("services") if isinstance(payload, dict) else None
    entry = services.get(service_id) if isinstance(services, dict) else None
    return entry if isinstance(entry, dict) else {}


def _write_cached_service(cache_path: Path, service_id: str, entry: dict) -> None:
    with _CACHE_LOCK:
        payload = _read_cache(cache_path)
        services = payload.get("services") if isinstance(payload.get("services"), dict) else {}
        services[service_id] = entry
        payload = {"version": _CACHE_VERSION, "services": services}
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_name(cache_path.name + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, cache_path)


def _read_cache(cache_path: Path) -> dict:
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": _CACHE_VERSION, "services": {}}
    if not isinstance(payload, dict) or payload.get("version") != _CACHE_VERSION:
        return {"version": _CACHE_VERSION, "services": {}}
    return payload


def _discovery_error_message(exc: Exception, has_cache: bool) -> str:
    suffix = "，已保留上次同步结果。" if has_cache else "，已保留内置模型和手工输入能力。"
    if isinstance(exc, HTTPError):
        if exc.code in {401, 403}:
            return "模型列表认证失败，请检查 API Key 或账号权限" + suffix
        return f"模型列表刷新失败（HTTP {exc.code}）" + suffix
    if isinstance(exc, (URLError, TimeoutError)):
        return "模型服务暂时无法连接" + suffix
    return "服务商没有返回可用的文本模型" + suffix
