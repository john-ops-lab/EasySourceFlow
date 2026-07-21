import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from easysourceflow_core.model_catalog import model_catalog


class _Response:
    def __init__(self, payload):
        self.body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self.body


class ModelCatalogTests(unittest.TestCase):
    def test_discovers_new_minimax_model_and_filters_non_summary_models(self):
        service = {
            "id": "minimax",
            "base_url": "https://api.minimaxi.com/v1",
            "models": ["MiniMax-M2.7"],
            "model_discovery": {"style": "openai"},
        }
        payload = {
            "data": [
                {"id": "MiniMax-M3", "owned_by": "minimax"},
                {"id": "speech-2.8-hd", "owned_by": "minimax"},
                {"id": "MiniMax-M2.7", "owned_by": "minimax"},
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "model-catalog.json"
            with patch("easysourceflow_core.model_catalog.urlopen", return_value=_Response(payload)) as fetch:
                result = model_catalog(service, "secret-key", cache_path, now=1000)

            self.assertEqual(result["status"], "live")
            self.assertEqual(result["model_ids"], ["MiniMax-M3", "MiniMax-M2.7"])
            self.assertEqual(result["additional_model_ids"], ["MiniMax-M3"])
            request = fetch.call_args.args[0]
            self.assertEqual(request.get_header("Authorization"), "Bearer secret-key")
            self.assertNotIn("secret-key", cache_path.read_text(encoding="utf-8"))
            self.assertNotIn("secret-key", json.dumps(result))

            with patch("easysourceflow_core.model_catalog.urlopen") as cached_fetch:
                cached = model_catalog(service, "secret-key", cache_path, now=1001)
            cached_fetch.assert_not_called()
            self.assertEqual(cached["status"], "cached")
            self.assertEqual(cached["model_ids"], result["model_ids"])

    def test_refresh_failure_keeps_cached_and_built_in_models(self):
        service = {
            "id": "kimi",
            "base_url": "https://api.moonshot.cn/v1",
            "models": ["kimi-k2.6"],
            "model_discovery": {"style": "openai"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "model-catalog.json"
            with patch(
                "easysourceflow_core.model_catalog.urlopen",
                return_value=_Response({"data": [{"id": "kimi-k3", "supports_reasoning": True}]}),
            ):
                model_catalog(service, "secret-key", cache_path, now=1000)
            with patch("easysourceflow_core.model_catalog.urlopen", side_effect=TimeoutError):
                result = model_catalog(
                    service,
                    "secret-key",
                    cache_path,
                    force_refresh=True,
                    now=1001,
                )

            self.assertEqual(result["status"], "fallback")
            self.assertEqual(result["model_ids"], ["kimi-k3"])
            self.assertIn("上次同步", result["message"])

    def test_requires_key_without_discarding_built_in_models(self):
        service = {
            "id": "kimi",
            "base_url": "https://api.moonshot.cn/v1",
            "models": ["kimi-k3", "kimi-k2.6"],
            "model_discovery": {"style": "openai"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            result = model_catalog(service, "", Path(tmp) / "cache.json")

        self.assertEqual(result["status"], "key_required")
        self.assertEqual(result["model_ids"], ["kimi-k3", "kimi-k2.6"])
        self.assertIn("填写 API Key", result["message"])

    def test_removed_key_does_not_present_cached_models_as_current(self):
        service = {
            "id": "kimi",
            "base_url": "https://api.moonshot.cn/v1",
            "models": ["kimi-k2.6"],
            "model_discovery": {"style": "openai"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "cache.json"
            with patch(
                "easysourceflow_core.model_catalog.urlopen",
                return_value=_Response({"data": [{"id": "kimi-k3"}]}),
            ):
                model_catalog(service, "secret-key", cache_path, now=1000)
            with patch("easysourceflow_core.model_catalog.urlopen") as fetch:
                result = model_catalog(service, "", cache_path, now=1001)

        fetch.assert_not_called()
        self.assertEqual(result["status"], "key_required")
        self.assertEqual(result["model_ids"], ["kimi-k3"])

    def test_gemini_discovery_only_keeps_generate_content_models(self):
        service = {
            "id": "gemini",
            "models": ["gemini-2.5-flash"],
            "model_discovery": {
                "style": "gemini",
                "url": "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000",
            },
        }
        payload = {
            "models": [
                {
                    "name": "models/gemini-3.5-flash",
                    "baseModelId": "gemini-3.5-flash",
                    "supportedGenerationMethods": ["generateContent"],
                },
                {
                    "name": "models/gemini-embedding-2",
                    "supportedGenerationMethods": ["embedContent"],
                },
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            with patch("easysourceflow_core.model_catalog.urlopen", return_value=_Response(payload)) as fetch:
                result = model_catalog(service, "gemini-key", Path(tmp) / "cache.json")

        self.assertEqual(result["model_ids"], ["gemini-3.5-flash"])
        self.assertEqual(fetch.call_args.args[0].get_header("X-goog-api-key"), "gemini-key")

    def test_ollama_discovery_uses_tags_endpoint_without_key(self):
        service = {
            "id": "ollama",
            "base_url": "http://127.0.0.1:11434/v1",
            "models": ["qwen3:8b"],
            "requires_api_key": False,
            "model_discovery": {"style": "ollama"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "easysourceflow_core.model_catalog.urlopen",
                return_value=_Response({"models": [{"model": "qwen3:14b"}]}),
            ) as fetch:
                result = model_catalog(service, "", Path(tmp) / "cache.json")

        self.assertEqual(result["model_ids"], ["qwen3:14b"])
        self.assertEqual(fetch.call_args.args[0].full_url, "http://127.0.0.1:11434/api/tags")


if __name__ == "__main__":
    unittest.main()
