"""Local smoke regression runner."""

from __future__ import annotations

import json
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

from .config import Settings
from .http_api import build_server


ARTICLE_HTML = """<!doctype html>
<html>
<head><title>EasySourceFlow Regression Article</title></head>
<body>
<article>
<h1>EasySourceFlow Regression Article</h1>
<p>This public local article verifies extraction, summary writing, and SQLite job tracking.</p>
<p>The smoke run also verifies local document submission and backup creation.</p>
</article>
</body>
</html>"""


class _ArticleHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        body = ARTICLE_HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_regression() -> dict:
    article_server = ThreadingHTTPServer(("127.0.0.1", 0), _ArticleHandler)
    _start(article_server)
    try:
        with tempfile.TemporaryDirectory(prefix="easysourceflow-regression-") as tmp:
            root = Path(tmp)
            settings = Settings(
                host="127.0.0.1",
                port=0,
                data_dir=root,
                database_path=root / "jobs.sqlite3",
                output_dir=root / "output",
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
            _start(api_server)
            try:
                base_url = f"http://127.0.0.1:{api_server.server_port}"
                article_url = f"http://127.0.0.1:{article_server.server_port}/article"
                article_job = _post(base_url + "/summarize", {"url": article_url, "instruction": "Summarize briefly."})
                document_job = _post(
                    base_url + "/documents",
                    {
                        "title": "regression.md",
                        "content": "Regression local document with enough readable content to summarize and store.",
                        "instruction": "Summarize this local document.",
                    },
                )
                backup = _post(base_url + "/backup", {})
                outputs = json.loads(urlopen(base_url + "/outputs", timeout=10).read().decode("utf-8"))
                return {
                    "ok": article_job["status"] == "succeeded" and document_job["status"] in {"queued", "running", "succeeded"} and backup["ok"],
                    "article_status": article_job["status"],
                    "document_status": document_job["status"],
                    "output_count": outputs["count"],
                    "backup_dir": backup["backup_dir"],
                }
            finally:
                api_server.shutdown()
                api_server.server_close()
    finally:
        article_server.shutdown()
        article_server.server_close()


def _start(server: ThreadingHTTPServer) -> None:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()


def _post(url: str, payload: dict) -> dict:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    result = run_regression()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
