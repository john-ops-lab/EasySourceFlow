import importlib.util
import tempfile
import threading
import unittest
from pathlib import Path

from easysourceflow_core.config import Settings
from easysourceflow_core.http_api import build_server


PLAYWRIGHT_AVAILABLE = importlib.util.find_spec("playwright") is not None


@unittest.skipUnless(PLAYWRIGHT_AVAILABLE, "Playwright is not installed")
class WebConsoleBrowserTests(unittest.TestCase):
    def test_primary_workflow_and_mobile_layout(self):
        from playwright.sync_api import sync_playwright

        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(tmp)
            server = build_server(settings)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f"http://127.0.0.1:{server.server_port}/"
            try:
                with sync_playwright() as playwright:
                    try:
                        browser = playwright.chromium.launch(headless=True)
                    except Exception as bundled_exc:
                        try:
                            browser = playwright.chromium.launch(channel="chrome", headless=True)
                        except Exception as chrome_exc:
                            self.skipTest(
                                "Chromium and system Chrome are unavailable: "
                                f"{type(bundled_exc).__name__}/{type(chrome_exc).__name__}"
                            )
                    page = browser.new_page(viewport={"width": 1440, "height": 960})
                    console_errors = []
                    page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
                    page.goto(url, wait_until="networkidle")
                    self.assertIn("EasySourceFlow", page.title())
                    self.assertTrue(page.locator("#submit-panel").is_visible())
                    page.locator(".advanced-settings summary").click()
                    self.assertTrue(page.locator("#force-refresh").is_visible())

                    page.locator('[data-tab="maintenance-panel"]').click()
                    self.assertEqual(page.locator("#bilibili-open-login-button").text_content(), "重新扫码接入")
                    self.assertEqual(page.locator("#youtube-open-login-button").text_content(), "重新登录接入")
                    self.assertTrue(page.locator("#bilibili-import-button").is_hidden())
                    self.assertTrue(page.locator("#youtube-import-button").is_hidden())
                    self.assertTrue(page.locator("#bilibili-logout-button").is_visible())
                    self.assertTrue(page.locator("#youtube-logout-button").is_visible())
                    self.assertIn("Chrome 当前登录态", page.locator("#youtube-account-status").text_content())
                    page.locator('[data-maintenance-tab="model-maintenance"]').click()
                    page.locator("#model-service").select_option("openai")
                    self.assertEqual(page.locator("#model-service").input_value(), "openai")
                    self.assertEqual(page.locator("#model-name").input_value(), "gpt-4.1-mini")
                    page.wait_for_timeout(5500)
                    self.assertEqual(page.locator("#model-service").input_value(), "openai")
                    self.assertTrue(page.locator("#model-unsaved-notice").is_visible())
                    self.assertTrue(page.locator("#settings-model-test-button").is_enabled())
                    self.assertEqual(page.locator("#settings-model-test-button").text_content(), "测试连接")
                    self.assertEqual(page.locator("#model-save-button").text_content(), "设为当前模型")
                    page.locator('[data-maintenance-tab="network-maintenance"]').click()
                    self.assertTrue(page.locator("#network-maintenance").is_visible())
                    self.assertEqual(page.locator("#network-security-pill").text_content(), "严格模式")
                    self.assertFalse(page.locator("#fake-ip-trust-enabled").is_checked())
                    self.assertEqual(page.locator("#fake-ip-cidrs").input_value(), "198.18.0.0/15")
                    page.locator('label[for="fake-ip-trust-enabled"]').click()
                    self.assertTrue(page.locator("#network-security-save").is_enabled())

                    original_url = page.url
                    with page.expect_popup() as result_popup:
                        page.locator('[data-tab="outputs-panel"]').click()
                    results_page = result_popup.value
                    results_page.wait_for_load_state("networkidle")
                    self.assertTrue(results_page.url.endswith("#results"))
                    self.assertTrue(results_page.locator("#outputs-panel").is_visible())
                    self.assertEqual(page.url, original_url)
                    results_page.close()
                    page.locator('[data-tab="submit-panel"]').click()

                    page.evaluate("activateComposerMode('file-mode')")
                    page.locator("#file-input").set_input_files(
                        {
                            "name": "browser-upload.txt",
                            "mimeType": "text/plain",
                            "buffer": b"This browser upload contains enough text to exercise the document workflow safely.",
                        }
                    )
                    with page.expect_response(
                        lambda response: response.url.endswith("/documents") and response.request.method == "POST"
                    ) as uploaded:
                        page.locator("#file-submit-button").click()
                    uploaded_job_id = uploaded.value.json()["job_id"]
                    page.locator("#file-status").wait_for(state="visible", timeout=15000)
                    self.assertIn(uploaded_job_id, page.locator("#file-status").text_content())
                    self.assertEqual(page.locator("#file-progress").get_attribute("value"), "100")

                    page.evaluate("activateComposerMode('link-mode')")
                    page.locator("#links").fill("not-a-url")
                    with page.expect_response(
                        lambda response: response.url.endswith("/jobs") and response.request.method == "POST"
                    ) as submitted:
                        page.locator("#submit-button").click()
                    job_id = submitted.value.json()["job_id"]
                    page.evaluate("jobId => showJob(jobId)", job_id)
                    page.locator("#retry-instruction").wait_for(state="visible", timeout=15000)
                    self.assertTrue(page.locator("#retry-force-refresh").is_checked())

                    page.set_viewport_size({"width": 390, "height": 844})
                    page.reload(wait_until="networkidle")
                    horizontal_overflow = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
                    self.assertFalse(horizontal_overflow)
                    composer_top = page.locator("#submit-panel .primary-card").bounding_box()["y"]
                    self.assertLess(composer_top, 220)
                    unexpected_errors = [
                        error for error in console_errors if "status of 400 (Bad Request)" not in error
                    ]
                    self.assertEqual(unexpected_errors, [])
                    browser.close()
            finally:
                server.shutdown()
                server.server_close()


def _settings(tmp: str) -> Settings:
    root = Path(tmp)
    secrets_dir = root / "data" / "secrets"
    secrets_dir.mkdir(parents=True)
    bilibili_cookies = secrets_dir / "bilibili-cookies.txt"
    bilibili_cookies.write_text(
        "# Netscape HTTP Cookie File\n.bilibili.com\tTRUE\t/\tFALSE\t0\tSESSDATA\tTEST_VALUE\n",
        encoding="utf-8",
    )
    youtube_cookies = secrets_dir / "youtube-cookies.txt"
    youtube_cookies.write_text(
        "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tLOGIN_INFO\tTEST_VALUE\n",
        encoding="utf-8",
    )
    return Settings(
        host="127.0.0.1",
        port=0,
        data_dir=root / "data",
        database_path=root / "jobs.sqlite3",
        output_dir=root / "output",
        allow_local_urls=False,
        request_timeout_seconds=2,
        max_content_chars=10000,
        ytdlp_path="",
        bilibili_cookies_file=str(bilibili_cookies),
        youtube_cookies_file=str(youtube_cookies),
        youtube_extractor_args="",
        youtube_browser_cookie_source="chrome:Default",
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


if __name__ == "__main__":
    unittest.main()
