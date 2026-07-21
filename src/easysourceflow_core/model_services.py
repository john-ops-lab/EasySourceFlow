"""Shared model-service definitions and configured failover profiles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


MODEL_SERVICES = [
    {
        "id": "local",
        "label": "本地基础摘要（非大模型）",
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
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "legacy_models": ["deepseek-v4-flash", "deepseek-v4-pro"],
        "default_model": "deepseek-chat",
        "strong_model": "deepseek-reasoner",
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
        "models": ["kimi-k3", "kimi-k2.7-code-highspeed", "kimi-k2.7-code", "kimi-k2.6", "moonshot-v1-128k"],
        "default_model": "kimi-k2.6",
        "strong_model": "kimi-k3",
        "model_discovery": {"style": "openai"},
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
        "models": ["MiniMax-M3", "MiniMax-M2.7-highspeed", "MiniMax-M2.7", "MiniMax-M2.5-highspeed", "MiniMax-M2.5"],
        "default_model": "MiniMax-M2.7-highspeed",
        "strong_model": "MiniMax-M3",
        "model_discovery": {"style": "openai"},
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

for _service in MODEL_SERVICES:
    if _service["provider"] != "local":
        _service.setdefault("model_discovery", {"style": "openai"})
for _service in MODEL_SERVICES:
    if _service["id"] == "gemini":
        _service["model_discovery"] = {
            "style": "gemini",
            "url": "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000",
        }
    elif _service["id"] == "ollama":
        _service["model_discovery"] = {"style": "ollama"}

MODEL_SERVICE_KEY_NAMES = {
    service["id"]: f"EASYSOURCEFLOW_MODEL_API_KEY_{service['id'].upper()}"
    for service in MODEL_SERVICES
    if service["id"] != "local"
}
MODEL_FALLBACK_SERVICE_KEY = "EASYSOURCEFLOW_MODEL_FALLBACK_SERVICE"


@dataclass(frozen=True)
class ModelProfile:
    service_id: str
    label: str
    provider: str
    model: str
    strong_model: str
    base_url: str
    api_key: str


def model_service_by_id(service_id: str) -> dict | None:
    return next((service for service in MODEL_SERVICES if service["id"] == service_id), None)


def model_service_for_config(provider: str, base_url: str) -> dict:
    if provider == "local":
        return model_service_by_id("local") or MODEL_SERVICES[0]
    return next(
        (service for service in MODEL_SERVICES if service["base_url"].rstrip("/") == base_url.rstrip("/")),
        model_service_by_id("deepseek") or MODEL_SERVICES[1],
    )


def model_service_is_configured(service: Mapping[str, object], values: Mapping[str, str]) -> bool:
    service_id = str(service["id"])
    api_key = str(values.get(MODEL_SERVICE_KEY_NAMES.get(service_id, ""), "")).strip()
    if service.get("requires_api_key", True):
        return bool(api_key)
    configured_flag = str(values.get(_profile_key("CONFIGURED", service_id), "")).strip().lower()
    return configured_flag in {"1", "true", "yes", "on"}


def configured_model_profiles(
    values: Mapping[str, str],
    active_service_id: str,
) -> tuple[ModelProfile, ...]:
    preferred = str(values.get(MODEL_FALLBACK_SERVICE_KEY, "")).strip().lower()
    services = [service for service in MODEL_SERVICES if service["id"] not in {"local", active_service_id}]
    services.sort(key=lambda service: 0 if service["id"] == preferred else 1)
    profiles = []
    for service in services:
        service_id = service["id"]
        api_key = str(values.get(MODEL_SERVICE_KEY_NAMES.get(service_id, ""), "")).strip()
        if not model_service_is_configured(service, values):
            continue
        profiles.append(
            ModelProfile(
                service_id=service_id,
                label=str(service["label"]),
                provider=str(service["provider"]),
                model=str(values.get(_profile_key("FAST", service_id)) or service["default_model"]),
                strong_model=str(values.get(_profile_key("PRO", service_id)) or service["strong_model"]),
                base_url=str(values.get(_profile_key("BASE_URL", service_id)) or service["base_url"]),
                api_key=api_key,
            )
        )
    return tuple(profiles)


def model_profile_env_values(service_id: str, model: str, strong_model: str, base_url: str) -> dict[str, str]:
    return {
        **model_profile_enabled_env_values(service_id, True),
        _profile_key("FAST", service_id): model,
        _profile_key("PRO", service_id): strong_model,
        _profile_key("BASE_URL", service_id): base_url,
    }


def model_profile_enabled_env_values(service_id: str, enabled: bool) -> dict[str, str]:
    return {_profile_key("CONFIGURED", service_id): "true" if enabled else "false"}


def _profile_key(kind: str, service_id: str) -> str:
    return f"EASYSOURCEFLOW_MODEL_{kind}_{service_id.upper()}"
