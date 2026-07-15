import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from base64 import b64encode
from unittest.mock import patch

from easysourceflow_core import __version__
from easysourceflow_core.config import Settings
from easysourceflow_core.http_api import _open_resource_package, build_server
from easysourceflow_mcp.server import (
    _favorite_result,
    _format_payload,
    _get_job_with_wait,
    _read_json,
    call_tool,
    handle_message,
)


ARTICLE_HTML = """<!doctype html>
<html>
<head><title>Local Test Article</title></head>
<body>
<article>
<h1>Local Test Article</h1>
<p>This article explains how an EasySourceFlow service extracts article text from public webpages.</p>
<p>The service stores every summarization job in SQLite so agents can recover previous work.</p>
<p>The MCP adapter exposes a small tool surface and keeps filesystem writes out of the default path.</p>
</article>
</body>
</html>"""


class ArticleHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_GET(self):
        body = ARTICLE_HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ErrorHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_GET(self):
        body = b"plain text failure"
        self.send_response(500)
        self.send_header("content-type", "text/plain")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start_server(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


class HttpAndMcpTests(unittest.TestCase):
    def test_web_media_download_is_persistent_and_not_an_mcp_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = Settings(
                host="127.0.0.1",
                port=0,
                data_dir=root / "data",
                database_path=root / "jobs.sqlite3",
                output_dir=root / "output",
                allow_local_urls=False,
                request_timeout_seconds=2,
                max_content_chars=10000,
                ytdlp_path="",
                bilibili_cookies_file="",
                youtube_cookies_file="",
                youtube_extractor_args="",
                ffmpeg_path="ffmpeg",
                whisper_cli_path="whisper-cli",
                whisper_model_path="",
                transcription_backend="whisper_cpp",
                mlx_whisper_path="mlx_whisper",
                faster_whisper_path="faster-whisper",
                max_transcription_seconds=7200,
                model_provider="local",
                model="local-extractive",
                strong_model="local-extractive",
                deepseek_api_key="",
                deepseek_base_url="https://example.com",
            )

            def fake_download(url, media_type, format_name, settings, destination, progress_callback=None, cancel_check=None):
                destination.mkdir(parents=True, exist_ok=True)
                path = destination / "示例音频.mp3"
                path.write_bytes(b"test-media")
                if progress_callback:
                    progress_callback("downloading", 0.75)
                return {
                    "operation": "media_download",
                    "source_url": url,
                    "canonical_url": url,
                    "source_type": "youtube",
                    "media_type": media_type,
                    "format": format_name,
                    "title": "示例音频",
                    "file_path": str(path.resolve()),
                    "file_name": path.name,
                    "file_size": path.stat().st_size,
                }

            with patch("easysourceflow_core.service.download_media", side_effect=fake_download):
                api_server = build_server(settings)
                start_server(api_server)
                base_url = f"http://127.0.0.1:{api_server.server_port}"
                try:
                    request = Request(
                        f"{base_url}/downloads",
                        data=json.dumps(
                            {
                                "url": "https://www.youtube.com/watch?v=example",
                                "media_type": "audio",
                                "format": "mp3",
                            }
                        ).encode("utf-8"),
                        headers={"content-type": "application/json"},
                        method="POST",
                    )
                    with urlopen(request, timeout=10) as response:
                        submitted = json.loads(response.read().decode("utf-8"))
                    job_id = submitted["job_id"]
                    completed = None
                    for _ in range(50):
                        with urlopen(f"{base_url}/downloads/{job_id}", timeout=10) as response:
                            completed = json.loads(response.read().decode("utf-8"))
                        if completed["status"] == "succeeded":
                            break
                        threading.Event().wait(0.02)
                    self.assertEqual(completed["status"], "succeeded")

                    with urlopen(f"{base_url}/downloads/{job_id}/file", timeout=10) as response:
                        self.assertEqual(response.read(), b"test-media")
                        self.assertIn("attachment", response.headers["content-disposition"])
                        self.assertEqual(response.headers["x-content-type-options"], "nosniff")

                    with urlopen(f"{base_url}/jobs?limit=20", timeout=10) as response:
                        jobs = json.loads(response.read().decode("utf-8"))
                    self.assertFalse(any(job["job_id"] == job_id for job in jobs["items"]))

                    generic_retry = Request(
                        f"{base_url}/jobs/{job_id}/retry",
                        data=b"{}",
                        headers={"content-type": "application/json"},
                        method="POST",
                    )
                    with self.assertRaises(HTTPError) as context:
                        urlopen(generic_retry, timeout=10)
                    self.assertEqual(context.exception.code, 404)
                    context.exception.close()

                    web_retry = Request(
                        f"{base_url}/downloads/{job_id}/retry",
                        data=b"{}",
                        headers={"content-type": "application/json"},
                        method="POST",
                    )
                    with urlopen(web_retry, timeout=10) as response:
                        retried = json.loads(response.read().decode("utf-8"))
                    self.assertEqual(retried["request_kind"], "media_download")
                    self.assertNotEqual(retried["job_id"], job_id)
                finally:
                    api_server.shutdown()
                    api_server.server_close()

        tools = handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]
        self.assertFalse(any("download" in tool["name"] for tool in tools))

    def test_http_api_updates_prompt_and_tracks_real_mcp_activity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace-agent"
            skill = workspace / "skills" / "easysourceflow" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("# test skill\n", encoding="utf-8")
            prompt_file = root / "config" / "summary-prompt.txt"
            settings = Settings(
                host="127.0.0.1",
                port=0,
                data_dir=root / "data",
                database_path=root / "jobs.sqlite3",
                output_dir=root / "output",
                allow_local_urls=False,
                request_timeout_seconds=2,
                max_content_chars=10000,
                ytdlp_path="",
                bilibili_cookies_file="",
                youtube_cookies_file="",
                youtube_extractor_args="",
                ffmpeg_path="ffmpeg",
                whisper_cli_path="whisper-cli",
                whisper_model_path="",
                transcription_backend="whisper_cpp",
                mlx_whisper_path="mlx_whisper",
                faster_whisper_path="faster-whisper",
                max_transcription_seconds=7200,
                model_provider="local",
                model="local-extractive",
                strong_model="local-extractive",
                deepseek_api_key="",
                deepseek_base_url="https://example.com",
                summary_prompt_file=prompt_file,
                agent_workspace=str(workspace),
            )
            with patch("easysourceflow_core.http_api._find_mcp_executable", return_value="/tmp/easysourceflow-mcp"):
                api_server = build_server(settings)
                start_server(api_server)
                base_url = f"http://127.0.0.1:{api_server.server_port}"
                try:
                    with urlopen(f"{base_url}/prompt", timeout=10) as response:
                        initial = json.loads(response.read().decode("utf-8"))
                    self.assertTrue(initial["is_default"])
                    self.assertIn("只根据来源内容总结", initial["prompt"])
                    self.assertIn("## 核心要点", initial["prompt"])
                    self.assertIn("## 质量检查", initial["prompt"])

                    custom_prompt = "硬性规则：只依据来源内容。\n\nMarkdown 模板要求：\n## 一句话结论\n## 核心要点"
                    request = Request(
                        f"{base_url}/prompt",
                        data=json.dumps({"prompt": custom_prompt}, ensure_ascii=False).encode("utf-8"),
                        headers={"content-type": "application/json"},
                        method="POST",
                    )
                    with urlopen(request, timeout=10) as response:
                        updated = json.loads(response.read().decode("utf-8"))
                    self.assertEqual(updated["prompt"], custom_prompt)
                    self.assertEqual(prompt_file.read_text(encoding="utf-8").strip(), custom_prompt)
                    self.assertEqual(settings.summary_prompt, custom_prompt)

                    with urlopen(f"{base_url}/agent/status", timeout=10) as response:
                        before = json.loads(response.read().decode("utf-8"))
                    self.assertEqual(before["state"], "ready")
                    self.assertFalse(before["activity"]["recent"])
                    self.assertNotIn(str(root), json.dumps(before, ensure_ascii=False))
                    self.assertEqual(before["mcp"]["command"], "<PROJECT_ROOT>/.venv/bin/easysourceflow-mcp")

                    heartbeat = Request(
                        f"{base_url}/health",
                        headers={"x-easysourceflow-client": "mcp"},
                        method="GET",
                    )
                    with urlopen(heartbeat, timeout=10) as response:
                        health = json.loads(response.read().decode("utf-8"))
                    self.assertEqual(health["version"], __version__)
                    with urlopen(f"{base_url}/agent/status", timeout=10) as response:
                        after = json.loads(response.read().decode("utf-8"))
                    self.assertEqual(after["state"], "connected")
                    self.assertTrue(after["activity"]["recent"])
                    self.assertEqual(after["activity"]["last_path"], "/health")
                finally:
                    api_server.shutdown()
                    api_server.server_close()

    def test_http_api_updates_model_and_imports_platform_cookies(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_file = Path(tmp) / "runtime.env"
            settings = Settings(
                host="127.0.0.1",
                port=0,
                data_dir=Path(tmp) / "data",
                database_path=Path(tmp) / "jobs.sqlite3",
                output_dir=Path(tmp) / "output",
                allow_local_urls=True,
                request_timeout_seconds=5,
                max_content_chars=10000,
                ytdlp_path=sys.executable,
                bilibili_cookies_file="",
                youtube_cookies_file="",
                youtube_extractor_args="",
                ffmpeg_path="ffmpeg",
                whisper_cli_path="whisper-cli",
                whisper_model_path="",
                transcription_backend="whisper_cpp",
                mlx_whisper_path="mlx_whisper",
                faster_whisper_path="faster-whisper",
                max_transcription_seconds=7200,
                model_provider="local",
                model="deepseek-v4-flash",
                strong_model="deepseek-v4-pro",
                deepseek_api_key="",
                deepseek_base_url="https://api.deepseek.com",
            )
            with patch.dict(os.environ, {"EASYSOURCEFLOW_CONFIG_FILE": str(config_file)}):
                api_server = build_server(settings)
                start_server(api_server)
                try:
                    model_payload = json.dumps(
                        {
                            "provider": "openai_compatible",
                            "model": "deepseek-v4-pro",
                            "strong_model": "deepseek-v4-pro",
                            "model_base_url": "https://api.deepseek.com",
                            "model_api_key": "test-model-api-key",
                        }
                    ).encode("utf-8")
                    model_request = Request(
                        f"http://127.0.0.1:{api_server.server_port}/model",
                        data=model_payload,
                        headers={"content-type": "application/json"},
                        method="POST",
                    )
                    with urlopen(model_request, timeout=10) as response:
                        model = json.loads(response.read().decode("utf-8"))
                    self.assertTrue(model["ok"])
                    self.assertEqual(model["model"]["provider"], "openai_compatible")
                    config_text = config_file.read_text(encoding="utf-8")
                    self.assertIn("EASYSOURCEFLOW_MODEL_PROVIDER=openai_compatible", config_text)
                    self.assertIn("EASYSOURCEFLOW_MODEL=deepseek-v4-pro", config_text)
                    self.assertIn("EASYSOURCEFLOW_MODEL_API_KEY=test-model-api-key", config_text)
                    self.assertIn("EASYSOURCEFLOW_MODEL_API_KEY_DEEPSEEK=test-model-api-key", config_text)
                    self.assertIn("DEEPSEEK_API_KEY=test-model-api-key", config_text)
                    self.assertTrue(model["model"]["model_api_key_configured"])
                    self.assertTrue(model["model"]["deepseek_api_key_configured"])
                    self.assertNotIn("test-model-api-key", json.dumps(model, ensure_ascii=False))

                    switch_payload = json.dumps(
                        {
                            "service_id": "openai",
                            "provider": "openai_compatible",
                            "model": "gpt-4.1-mini",
                            "strong_model": "gpt-4.1",
                            "model_base_url": "https://api.openai.com/v1",
                        }
                    ).encode("utf-8")
                    switch_request = Request(
                        f"http://127.0.0.1:{api_server.server_port}/model",
                        data=switch_payload,
                        headers={"content-type": "application/json"},
                        method="POST",
                    )
                    with urlopen(switch_request, timeout=10) as response:
                        switched = json.loads(response.read().decode("utf-8"))
                    self.assertEqual(switched["model"]["active_service_id"], "openai")
                    self.assertFalse(switched["model"]["model_api_key_configured"])
                    switched_config = config_file.read_text(encoding="utf-8")
                    self.assertIn("EASYSOURCEFLOW_MODEL_API_KEY=\n", switched_config)
                    self.assertIn("EASYSOURCEFLOW_MODEL_API_KEY_DEEPSEEK=test-model-api-key", switched_config)

                    restore_payload = json.dumps(
                        {
                            "service_id": "deepseek",
                            "provider": "openai_compatible",
                            "model": "deepseek-v4-pro",
                            "strong_model": "deepseek-v4-pro",
                            "model_base_url": "https://api.deepseek.com",
                        }
                    ).encode("utf-8")
                    restore_request = Request(
                        f"http://127.0.0.1:{api_server.server_port}/model",
                        data=restore_payload,
                        headers={"content-type": "application/json"},
                        method="POST",
                    )
                    with urlopen(restore_request, timeout=10) as response:
                        restored = json.loads(response.read().decode("utf-8"))
                    self.assertEqual(restored["model"]["active_service_id"], "deepseek")
                    self.assertTrue(restored["model"]["model_api_key_configured"])

                    clear_payload = json.dumps(
                        {
                            "service_id": "deepseek",
                            "provider": "openai_compatible",
                            "model": "deepseek-v4-pro",
                            "strong_model": "deepseek-v4-pro",
                            "model_base_url": "https://api.deepseek.com",
                            "clear_model_api_key": True,
                        }
                    ).encode("utf-8")
                    clear_request = Request(
                        f"http://127.0.0.1:{api_server.server_port}/model",
                        data=clear_payload,
                        headers={"content-type": "application/json"},
                        method="POST",
                    )
                    with urlopen(clear_request, timeout=10) as response:
                        cleared = json.loads(response.read().decode("utf-8"))
                    self.assertFalse(cleared["model"]["model_api_key_configured"])
                    self.assertFalse(cleared["model"]["deepseek_api_key_configured"])
                    self.assertIn("EASYSOURCEFLOW_MODEL_API_KEY=", config_file.read_text(encoding="utf-8"))
                    self.assertIn("DEEPSEEK_API_KEY=", config_file.read_text(encoding="utf-8"))

                    with patch("easysourceflow_core.http_api.webbrowser.open", return_value=True):
                        open_request = Request(
                            f"http://127.0.0.1:{api_server.server_port}/bilibili/login/open",
                            data=b"{}",
                            headers={"content-type": "application/json"},
                            method="POST",
                        )
                        with urlopen(open_request, timeout=10) as response:
                            opened = json.loads(response.read().decode("utf-8"))
                    self.assertTrue(opened["ok"])

                    def fake_run(command, **_kwargs):
                        cookies_path = Path(command[command.index("--cookies") + 1])
                        cookies_path.parent.mkdir(parents=True, exist_ok=True)
                        if "youtube.com" in command[-1]:
                            cookies_path.write_text(
                                "# Netscape HTTP Cookie File\n"
                                "#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t0\tLOGIN_INFO\tYOUTUBE_TEST_VALUE\n"
                                ".example.com\tTRUE\t/\tFALSE\t0\tUNRELATED\tSHOULD_NOT_PERSIST\n",
                                encoding="utf-8",
                            )
                        else:
                            cookies_path.write_text(
                                "# Netscape HTTP Cookie File\n"
                                ".bilibili.com\tTRUE\t/\tFALSE\t0\tFAKE_COOKIE\ttest\n"
                                ".example.com\tTRUE\t/\tFALSE\t0\tUNRELATED\tSHOULD_NOT_PERSIST\n",
                                encoding="utf-8",
                            )
                        return subprocess.CompletedProcess(command, 0, "", "")

                    with patch("easysourceflow_core.http_api.subprocess.run", side_effect=fake_run):
                        import_request = Request(
                            f"http://127.0.0.1:{api_server.server_port}/cookies/bilibili/import",
                            data=b"{}",
                            headers={"content-type": "application/json"},
                            method="POST",
                        )
                        with urlopen(import_request, timeout=10) as response:
                            imported = json.loads(response.read().decode("utf-8"))
                    self.assertTrue(imported["ok"])
                    self.assertTrue(imported["cookies"]["ok"])
                    self.assertIn("EASYSOURCEFLOW_BILIBILI_COOKIES_FILE=", config_file.read_text(encoding="utf-8"))
                    self.assertNotIn("FAKE_COOKIE", json.dumps(imported, ensure_ascii=False))
                    bilibili_cookie_text = Path(settings.bilibili_cookies_file).read_text(encoding="utf-8")
                    self.assertIn(".bilibili.com", bilibili_cookie_text)
                    self.assertNotIn(".example.com", bilibili_cookie_text)

                    with patch("easysourceflow_core.http_api.subprocess.run", side_effect=fake_run):
                        youtube_request = Request(
                            f"http://127.0.0.1:{api_server.server_port}/cookies/youtube/import",
                            data=b"{}",
                            headers={"content-type": "application/json"},
                            method="POST",
                        )
                        with urlopen(youtube_request, timeout=10) as response:
                            youtube_imported = json.loads(response.read().decode("utf-8"))
                    self.assertTrue(youtube_imported["ok"])
                    self.assertTrue(youtube_imported["cookies"]["ok"])
                    self.assertTrue(youtube_imported["cookies"]["authenticated"])
                    self.assertTrue(youtube_imported["cookies"]["browser_cookie_source_configured"])
                    self.assertEqual(youtube_imported["cookies"]["browser_cookie_source"], "chrome:Default")
                    self.assertEqual(youtube_imported["cookies"]["cookie_count"], 1)
                    self.assertIn("EASYSOURCEFLOW_YOUTUBE_COOKIES_FILE=", config_file.read_text(encoding="utf-8"))
                    self.assertIn(
                        "EASYSOURCEFLOW_YOUTUBE_BROWSER_COOKIE_SOURCE=chrome:Default",
                        config_file.read_text(encoding="utf-8"),
                    )
                    self.assertNotIn("YOUTUBE_TEST_VALUE", json.dumps(youtube_imported, ensure_ascii=False))
                    youtube_cookie_text = Path(settings.youtube_cookies_file).read_text(encoding="utf-8")
                    self.assertIn(".youtube.com", youtube_cookie_text)
                    self.assertNotIn(".example.com", youtube_cookie_text)
                finally:
                    api_server.shutdown()
                    api_server.server_close()

    def test_http_api_summarizes_local_article_and_records_job(self):
        article_server = ThreadingHTTPServer(("127.0.0.1", 0), ArticleHandler)
        start_server(article_server)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                settings = Settings(
                    host="127.0.0.1",
                    port=0,
                    data_dir=Path(tmp),
                    database_path=Path(tmp) / "jobs.sqlite3",
                    output_dir=Path(tmp) / "output",
                    allow_local_urls=True,
                    request_timeout_seconds=5,
                    max_content_chars=10000,
                    ytdlp_path="",
                    bilibili_cookies_file="",
                    youtube_cookies_file="",
                    youtube_extractor_args="",
                    ffmpeg_path="ffmpeg",
                    whisper_cli_path="whisper-cli",
                    whisper_model_path="",
                    transcription_backend="whisper_cpp",
                    mlx_whisper_path="mlx_whisper",
                    faster_whisper_path="faster-whisper",
                    max_transcription_seconds=7200,
                    model_provider="local",
                    model="deepseek-v4-flash",
                    strong_model="deepseek-v4-pro",
                    deepseek_api_key="",
                    deepseek_base_url="https://api.deepseek.com",
                )
                api_server = build_server(settings)
                start_server(api_server)
                try:
                    url = f"http://127.0.0.1:{article_server.server_port}/article"
                    payload = json.dumps({"url": url, "instruction": "Summarize briefly."}).encode("utf-8")
                    request = Request(
                        f"http://127.0.0.1:{api_server.server_port}/summarize",
                        data=payload,
                        headers={"content-type": "application/json"},
                        method="POST",
                    )
                    with urlopen(request, timeout=10) as response:
                        data = json.loads(response.read().decode("utf-8"))
                    self.assertEqual(data["status"], "succeeded")
                    self.assertIn("Local Test Article", data["result"]["summary_markdown"])
                    output_path = Path(data["result"]["output_markdown_path"])
                    self.assertTrue(output_path.exists())
                    self.assertIn("output", output_path.parts)
                    self.assertEqual(output_path.parent.name, "web")
                    self.assertRegex(output_path.name, r"^\d{6}-")
                    self.assertIn("Local Test Article", output_path.read_text(encoding="utf-8"))
                    latest_path = output_path.parent / "latest.md"
                    self.assertTrue(latest_path.exists())
                    self.assertIn("Local Test Article", latest_path.read_text(encoding="utf-8"))
                    self.assertTrue((Path(tmp) / "jobs.sqlite3").exists())

                    with urlopen(f"http://127.0.0.1:{api_server.server_port}/", timeout=10) as response:
                        html = response.read().decode("utf-8")
                    self.assertIn("EasySourceFlow", html)
                    self.assertIn("开始总结", html)

                    with urlopen(f"http://127.0.0.1:{api_server.server_port}/outputs", timeout=10) as response:
                        outputs = json.loads(response.read().decode("utf-8"))
                    self.assertEqual(outputs["count"], 1)
                    self.assertEqual(outputs["source_counts"]["web"], 1)
                    self.assertEqual(outputs["items"][0]["date"], output_path.parents[1].name)
                    self.assertEqual(outputs["items"][0]["output_markdown_path"], str(output_path.resolve()))
                    with urlopen(
                        f"http://127.0.0.1:{api_server.server_port}{outputs['items'][0]['view_url']}",
                        timeout=10,
                    ) as response:
                        output_html = response.read().decode("utf-8")
                    self.assertIn("Local Test Article", output_html)
                    self.assertIn("复制 Markdown", output_html)

                    with urlopen(f"http://127.0.0.1:{api_server.server_port}/search?q=SQLite", timeout=10) as response:
                        search = json.loads(response.read().decode("utf-8"))
                    self.assertGreaterEqual(search["count"], 1)

                    with urlopen(f"http://127.0.0.1:{api_server.server_port}/cookies/bilibili", timeout=10) as response:
                        cookies = json.loads(response.read().decode("utf-8"))
                    self.assertFalse(cookies["configured"])

                    with urlopen(f"http://127.0.0.1:{api_server.server_port}/model", timeout=10) as response:
                        model = json.loads(response.read().decode("utf-8"))
                    self.assertEqual(model["provider"], "local")
                    self.assertIn("openai_compatible", model["available_providers"])

                    with urlopen(f"http://127.0.0.1:{api_server.server_port}/maintenance/status", timeout=10) as response:
                        maintenance = json.loads(response.read().decode("utf-8"))
                    self.assertEqual(maintenance["status"], "never_run")

                    payload = json.dumps({"url": url, "instruction": "Summarize briefly."}).encode("utf-8")
                    cached_request = Request(
                        f"http://127.0.0.1:{api_server.server_port}/summarize",
                        data=payload,
                        headers={"content-type": "application/json"},
                        method="POST",
                    )
                    with urlopen(cached_request, timeout=10) as response:
                        cached_job = json.loads(response.read().decode("utf-8"))
                    self.assertEqual(cached_job["status"], "succeeded")
                    self.assertTrue(cached_job["result"].get("cache_hit"))

                    retry_request = Request(
                        f"http://127.0.0.1:{api_server.server_port}/jobs/{cached_job['job_id']}/retry",
                        data=b"{}",
                        headers={"content-type": "application/json"},
                        method="POST",
                    )
                    with urlopen(retry_request, timeout=10) as response:
                        retry_job = json.loads(response.read().decode("utf-8"))
                    self.assertIn(retry_job["status"], {"queued", "running", "succeeded"})

                    document_payload = json.dumps(
                        {
                            "title": "notes.md",
                            "content": "These local notes describe SQLite jobs, retry operations, and Markdown output.",
                            "instruction": "Summarize the local note.",
                        }
                    ).encode("utf-8")
                    document_request = Request(
                        f"http://127.0.0.1:{api_server.server_port}/documents",
                        data=document_payload,
                        headers={"content-type": "application/json"},
                        method="POST",
                    )
                    with urlopen(document_request, timeout=10) as response:
                        document_job = json.loads(response.read().decode("utf-8"))
                    self.assertIn(document_job["status"], {"queued", "running", "succeeded"})

                    html_document_payload = json.dumps(
                        {
                            "title": "clip.html",
                            "data_base64": b64encode(b"<html><body><article>HTML document upload body text for regression.</article></body></html>").decode("ascii"),
                            "mime_type": "text/html",
                            "instruction": "Summarize the HTML clip.",
                        }
                    ).encode("utf-8")
                    html_document_request = Request(
                        f"http://127.0.0.1:{api_server.server_port}/documents",
                        data=html_document_payload,
                        headers={"content-type": "application/json"},
                        method="POST",
                    )
                    with urlopen(html_document_request, timeout=10) as response:
                        html_document_job = json.loads(response.read().decode("utf-8"))
                    self.assertIn(html_document_job["status"], {"queued", "running", "succeeded"})

                    with urlopen(f"http://127.0.0.1:{api_server.server_port}/queue", timeout=10) as response:
                        queue = json.loads(response.read().decode("utf-8"))
                    self.assertIn("counts", queue)
                    self.assertIn("active_count", queue)

                    batch_payload = json.dumps({"urls": [url], "instruction": "Summarize briefly."}).encode("utf-8")
                    batch_request = Request(
                        f"http://127.0.0.1:{api_server.server_port}/batches",
                        data=batch_payload,
                        headers={"content-type": "application/json"},
                        method="POST",
                    )
                    with urlopen(batch_request, timeout=10) as response:
                        batch = json.loads(response.read().decode("utf-8"))
                    self.assertEqual(batch["count"], 1)
                    self.assertEqual(len(batch["job_ids"]), 1)
                    batch_id = batch["batch_id"]
                    with urlopen(f"http://127.0.0.1:{api_server.server_port}/batches/{batch_id}", timeout=10) as response:
                        batch_status = json.loads(response.read().decode("utf-8"))
                    self.assertEqual(batch_status["count"], 1)
                    self.assertIn("summary", batch_status)
                    self.assertIn("succeeded", batch_status["summary"])
                    with urlopen(f"http://127.0.0.1:{api_server.server_port}/batches?limit=10", timeout=10) as response:
                        batches = json.loads(response.read().decode("utf-8"))
                    self.assertEqual(len(batches["items"]), 1)
                    self.assertEqual(batches["items"][0]["batch_id"], batch_id)

                    cleanup_payload = json.dumps({"days": 0, "dry_run": True}).encode("utf-8")
                    cleanup_request = Request(
                        f"http://127.0.0.1:{api_server.server_port}/cleanup",
                        data=cleanup_payload,
                        headers={"content-type": "application/json"},
                        method="POST",
                    )
                    with urlopen(cleanup_request, timeout=10) as response:
                        cleanup = json.loads(response.read().decode("utf-8"))
                    self.assertTrue(cleanup["dry_run"])
                    self.assertIn("categories", cleanup)

                    backup_request = Request(
                        f"http://127.0.0.1:{api_server.server_port}/backup",
                        data=b"{}",
                        headers={"content-type": "application/json"},
                        method="POST",
                    )
                    with urlopen(backup_request, timeout=10) as response:
                        backup = json.loads(response.read().decode("utf-8"))
                    self.assertTrue(backup["ok"])
                    self.assertTrue(Path(backup["backup_dir"]).exists())
                finally:
                    api_server.shutdown()
                    api_server.server_close()
        finally:
            article_server.shutdown()
            article_server.server_close()

    def test_mcp_adapter_lists_tools(self):
        env = os.environ.copy()
        src_path = str(Path(__file__).resolve().parents[1] / "src")
        env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.Popen(
            [sys.executable, "-m", "easysourceflow_mcp.server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        try:
            proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}) + "\n")
            proc.stdin.flush()
            init_response = json.loads(proc.stdout.readline())
            self.assertEqual(init_response["result"]["serverInfo"]["name"], "easysourceflow_mcp")
            self.assertEqual(init_response["result"]["serverInfo"]["version"], __version__)

            proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}) + "\n")
            proc.stdin.flush()
            tools_response = json.loads(proc.stdout.readline())
            names = {tool["name"] for tool in tools_response["result"]["tools"]}
            self.assertIn("easysourceflow_summarize_link", names)
            self.assertIn("easysourceflow_submit_link", names)
            self.assertIn("easysourceflow_get_job", names)
            self.assertIn("easysourceflow_favorite_result", names)
            self.assertIn("easysourceflow_submit_batch", names)
            self.assertIn("easysourceflow_get_batch", names)
            self.assertIn("easysourceflow_retry_job", names)
            self.assertIn("easysourceflow_cancel_job", names)
            self.assertIn("easysourceflow_submit_document", names)
            self.assertIn("easysourceflow_search_outputs", names)
            self.assertIn("easysourceflow_bilibili_cookie_status", names)
            self.assertIn("easysourceflow_model_status", names)
            self.assertIn("easysourceflow_health_check", names)
            self.assertIn("easysourceflow_cleanup", names)
            self.assertIn("easysourceflow_backup", names)
            for tool in tools_response["result"]["tools"]:
                self.assertFalse(tool["inputSchema"]["additionalProperties"])
                self.assertIn("readOnlyHint", tool["annotations"])
                self.assertIn("destructiveHint", tool["annotations"])
        finally:
            proc.terminate()
            proc.wait(timeout=5)
            proc.stdin.close()
            proc.stdout.close()
            proc.stderr.close()

    def test_mcp_read_json_handles_non_json_http_errors(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), ErrorHandler)
        start_server(server)
        try:
            payload = _read_json(Request(f"http://127.0.0.1:{server.server_port}/error", method="GET"))
        finally:
            server.shutdown()
            server.server_close()
        self.assertIn("error", payload)
        self.assertEqual(payload["error"]["code"], "http_error")
        self.assertIn("plain text failure", payload["error"]["message"])

    def test_open_resource_package_restricts_path_to_output_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "output"
            package = output_dir / "2026-07-14" / "bilibili" / "sample"
            package.mkdir(parents=True)
            with patch("easysourceflow_core.http_api.subprocess.Popen") as popen, patch(
                "easysourceflow_core.http_api.sys.platform", "darwin"
            ):
                result = _open_resource_package(output_dir, str(package))

            self.assertTrue(result["ok"])
            popen.assert_called_once()
            with self.assertRaises(FileNotFoundError):
                _open_resource_package(output_dir, str(Path(tmp) / "outside"))

    def test_mcp_favorite_result_uses_output_markdown_path(self):
        calls = []

        def fake_get(path):
            calls.append(("get", path))
            if path == "/outputs":
                return {
                    "items": [
                        {
                            "relative_path": "bilibili/260630/test.md",
                            "output_markdown_path": "/tmp/result.md",
                        }
                    ]
                }
            return {}

        def fake_post(path, payload):
            calls.append(("post", path, payload))
            return {"ok": True, "relative_path": payload["relative_path"]}

        with patch("easysourceflow_mcp.server._get_json", side_effect=fake_get), patch(
            "easysourceflow_mcp.server._post_json", side_effect=fake_post
        ):
            payload = _favorite_result({"output_markdown_path": "/tmp/result.md"})

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["message"], "已收藏这篇总结。")
        self.assertIn(("post", "/favorites", {"relative_path": "bilibili/260630/test.md"}), calls)

    def test_mcp_summary_payload_marks_markdown_as_final(self):
        text = _format_payload(
            {
                "result": {
                    "summary_markdown": "# Title\n\n## 一句话结论\n正文",
                    "output_markdown_path": "/tmp/result.md",
                }
            }
        )
        self.assertIn("EasySourceFlow final Markdown", text)
        self.assertIn("Relay the Markdown below verbatim", text)
        self.assertIn("message tool `card`", text)
        self.assertIn("never put card JSON in `message`", text)
        self.assertIn("easysourceflow_favorite_result", text)
        self.assertIn("output_markdown_path=/tmp/result.md", text)
        self.assertIn("# Title", text)

    def test_mcp_rejects_invalid_tool_arguments_without_http_call(self):
        with patch("easysourceflow_mcp.server._post_json") as post_json, patch(
            "easysourceflow_mcp.server._get_json"
        ) as get_json:
            missing = call_tool("easysourceflow_summarize_link", {})
            wrong_type = call_tool("easysourceflow_submit_batch", {"urls": "https://example.com"})
            unknown = call_tool("easysourceflow_health_check", {"verbose": True})
            excessive_wait = call_tool("easysourceflow_get_job", {"job_id": "job_1", "wait_seconds": 46})

        self.assertTrue(missing["isError"])
        self.assertIn("'url' is required", missing["content"][0]["text"])
        self.assertTrue(wrong_type["isError"])
        self.assertIn("must be array", wrong_type["content"][0]["text"])
        self.assertTrue(unknown["isError"])
        self.assertIn("unknown field 'verbose'", unknown["content"][0]["text"])
        self.assertTrue(excessive_wait["isError"])
        self.assertIn("above the maximum", excessive_wait["content"][0]["text"])
        post_json.assert_not_called()
        get_json.assert_not_called()

    def test_mcp_sync_video_requires_async_without_http_call(self):
        with patch("easysourceflow_mcp.server._post_json") as post_json:
            result = call_tool(
                "easysourceflow_summarize_link",
                {"url": "https://www.bilibili.com/video/BV1example"},
            )

        self.assertTrue(result["isError"])
        self.assertEqual(result["structuredContent"]["error"]["code"], "video_requires_async")
        self.assertIn("easysourceflow_submit_link", result["content"][0]["text"])
        post_json.assert_not_called()

    def test_mcp_sync_short_webpage_remains_compatible(self):
        response = {"status": "succeeded", "result": {"summary_markdown": "# Result"}}
        with patch("easysourceflow_mcp.server._post_json", return_value=response) as post_json:
            result = call_tool("easysourceflow_summarize_link", {"url": "https://example.com/article"})

        self.assertFalse(result["isError"])
        self.assertEqual(result["structuredContent"], response)
        post_json.assert_called_once_with(
            "/summarize",
            {
                "url": "https://example.com/article",
                "instruction": "",
                "summary_quality": "fast",
                "force_refresh": False,
            },
        )

    def test_mcp_get_job_waits_until_succeeded(self):
        responses = [
            {"job_id": "job_1", "status": "queued"},
            {"job_id": "job_1", "status": "succeeded", "result": {"summary_markdown": "# Done"}},
        ]
        with patch("easysourceflow_mcp.server._get_json", side_effect=responses) as get_json, patch(
            "easysourceflow_mcp.server.time.monotonic", side_effect=[0.0, 0.0, 0.5]
        ), patch("easysourceflow_mcp.server.time.sleep") as sleep:
            payload = _get_job_with_wait("job_1", 1)

        self.assertEqual(payload["status"], "succeeded")
        self.assertNotIn("polling", payload)
        self.assertEqual(get_json.call_count, 2)
        sleep.assert_called_once_with(0.5)

    def test_mcp_get_job_running_response_requires_repeat_without_fallback(self):
        with patch(
            "easysourceflow_mcp.server._get_json",
            return_value={"job_id": "job_1", "status": "running"},
        ):
            result = call_tool("easysourceflow_get_job", {"job_id": "job_1", "wait_seconds": 0})

        self.assertFalse(result["isError"])
        polling = result["structuredContent"]["polling"]
        self.assertFalse(polling["complete"])
        self.assertFalse(polling["fallback_allowed"])
        self.assertIn("same job_id", polling["next_action"])

    def test_mcp_returns_structured_content(self):
        with patch("easysourceflow_mcp.server._get_json", return_value={"ok": True, "checks": []}):
            result = call_tool("easysourceflow_health_check", {})

        self.assertFalse(result["isError"])
        self.assertEqual(result["structuredContent"], {"ok": True, "checks": []})

    def test_mcp_invalid_request_returns_json_rpc_error(self):
        response = handle_message(["not", "an", "object"])
        self.assertEqual(response["error"]["code"], -32600)

        response = handle_message({"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": []})
        self.assertEqual(response["error"]["code"], -32602)


if __name__ == "__main__":
    unittest.main()
