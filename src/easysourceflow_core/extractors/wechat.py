"""WeChat public account article extraction."""

from __future__ import annotations

import html
import os
import re
import shlex
import subprocess
import atexit
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from easysourceflow_core.config import Settings
from easysourceflow_core.errors import extraction_error, extraction_failed
from easysourceflow_core.models import SourceDocument
from easysourceflow_core.url_utils import normalize_url


WECHAT_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
    "Mobile/15E148 Safari/604.1 MicroMessenger/8.0.50"
)

_BROWSER_LOCK = threading.Lock()
_PLAYWRIGHT = None
_BROWSER = None


def extract_wechat_document(url: str, settings: Settings) -> SourceDocument:
    canonical_url = normalize_url(url, settings.allow_local_urls, settings.trusted_fake_ip_cidrs)
    try:
        page_html = _fetch_wechat_html(canonical_url, settings.request_timeout_seconds)
        _raise_for_wechat_block_page(page_html)
    except Exception as exc:
        fallback = _fallback_wechat_document(canonical_url, settings)
        if fallback:
            return fallback
        raise exc

    title, author, published_at, text = _extract_wechat_fields(page_html)
    markdown = _external_wechat_markdown(canonical_url, settings.request_timeout_seconds)
    extraction_method = "wechat_meta_or_body"
    if len(markdown) > max(len(text), 80):
        text = _normalize_lines(_strip_html(markdown))
        extraction_method = "wechat_external_markdown"

    if len(text) < 80:
        fallback = _fallback_wechat_document(canonical_url, settings)
        if fallback:
            return fallback
        raise extraction_error(
            "wechat_browser_fallback_needed",
            "Could not extract enough readable WeChat article text with the lightweight extractor.",
            [
                "Install Playwright browser support or configure EASYSOURCEFLOW_WECHAT_MARKDOWN_COMMAND.",
                "Open the article in a browser to confirm it is publicly readable.",
            ],
        )

    if len(text) > settings.max_content_chars:
        text = text[: settings.max_content_chars].rsplit("\n", 1)[0]
    if len(markdown) > settings.max_content_chars:
        markdown = markdown[: settings.max_content_chars].rsplit("\n", 1)[0]

    return SourceDocument(
        source_url=url,
        canonical_url=canonical_url,
        source_type="wechat",
        title=title or canonical_url,
        author=author,
        published_at=published_at,
        language="zh",
        content_text=text,
        content_markdown=markdown or text,
        metadata={"image_urls": _extract_image_urls(page_html)},
        extraction_method=extraction_method,
    )


def _fetch_wechat_html(url: str, timeout_seconds: float) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": WECHAT_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except Exception as exc:
        if getattr(exc, "code", None):
            raise extraction_failed(f"Could not fetch WeChat article; HTTP status {exc.code}.") from exc
        raise extraction_failed(f"Could not fetch WeChat article: {type(exc).__name__}.") from exc


def _extract_wechat_fields(page_html: str) -> Tuple[str, Optional[str], Optional[str], str]:
    soup = BeautifulSoup(page_html, "html.parser")
    title = (
        _node_text(soup, "#activity-name")
        or _node_text(soup, "h1.rich_media_title")
        or _regex_var(page_html, "msg_title")
        or _first_meta(soup, "og:title")
        or ""
    )
    author = (
        _node_text(soup, "#js_name")
        or _node_text(soup, ".profile_nickname")
        or _regex_var(page_html, "nickname")
        or _first_meta(soup, "og:article:author")
        or None
    )
    published_at = _published_at(page_html)

    body_text = _body_text(soup)
    if not body_text:
        description = _first_meta(soup, "og:description") or _meta_name(soup, "description") or ""
        body_text = _strip_html(_decode_wechat_escaped_text(description))

    return (
        _decode_wechat_escaped_text(title),
        _decode_wechat_escaped_text(author) if author else None,
        published_at,
        _normalize_lines(body_text),
    )


def _body_text(soup: BeautifulSoup) -> str:
    for selector in ["#js_content", ".rich_media_content", "article"]:
        node = soup.select_one(selector)
        if not node:
            continue
        for tag in node(["script", "style", "svg", "canvas", "form"]):
            tag.decompose()
        for image in node.find_all("img"):
            image.replace_with("\n[图片]\n")
        text = _normalize_lines(node.get_text("\n", strip=True))
        if len(text) >= 80:
            return text
    return ""


def _first_meta(soup: BeautifulSoup, property_name: str) -> str:
    node = soup.find("meta", {"property": property_name})
    return node.get("content", "") if node else ""


def _meta_name(soup: BeautifulSoup, name: str) -> str:
    node = soup.find("meta", {"name": name})
    return node.get("content", "") if node else ""


def _node_text(soup: BeautifulSoup, selector: str) -> str:
    node = soup.select_one(selector)
    return node.get_text(" ", strip=True) if node else ""


def _regex_var(page_html: str, name: str) -> str:
    escaped = re.escape(name)
    match = re.search(
        rf"(?:var\s+|window\.){escaped}\s*=\s*(?:window\.title\s*=\s*)?(['\"])(.*?)\1",
        page_html,
        re.DOTALL,
    )
    if match:
        return match.group(2)
    match = re.search(rf"window\\.{escaped}\\s*=\\s*(?:window\\.title\\s*=\\s*)?'([^']*)'", page_html)
    return match.group(1) if match else ""


def _published_at(page_html: str) -> Optional[str]:
    soup = BeautifulSoup(page_html, "html.parser")
    visible_time = _node_text(soup, "#publish_time")
    if visible_time:
        return visible_time

    match = re.search(r"(?:var\s+|window\.)ct\s*=\s*['\"]?(\d+)['\"]?", page_html)
    if not match:
        match = re.search(r"window\\.ct\\s*=\\s*'?(\\d+)'?", page_html)
    if not match:
        return None
    timestamp = int(match.group(1))
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat(timespec="seconds")


def _decode_wechat_escaped_text(value: str) -> str:
    if not value:
        return ""
    text = re.sub(
        r"\\x([0-9a-fA-F]{2})",
        lambda match: chr(int(match.group(1), 16)),
        value,
    )
    return html.unescape(text)


def _normalize_lines(text: str) -> str:
    lines = []
    for raw in re.split(r"[\r\n]+", _decode_wechat_escaped_text(text)):
        line = re.sub(r"\s+", " ", raw).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def _strip_html(value: str) -> str:
    if "<" not in value or ">" not in value:
        return value
    return BeautifulSoup(value, "html.parser").get_text("\n", strip=True)


def _raise_for_wechat_block_page(page_html: str) -> None:
    checks = {
        "请输入验证码": "WeChat requires a verification code for this request.",
        "访问过于频繁": "WeChat is rate-limiting this machine.",
        "当前环境异常": "WeChat blocked this request because the browser environment looks abnormal.",
        "关注后查看": "This article requires following the account before viewing the full content.",
        "该内容已被发布者删除": "This WeChat article has been deleted by the publisher.",
        "此内容因违规无法查看": "This WeChat article is not viewable because it was restricted by WeChat.",
    }
    for marker, message in checks.items():
        if marker in page_html:
            raise extraction_error(
                "wechat_blocked",
                message,
                [
                    "Retry later or use a browser-based extractor.",
                    "Confirm the article is public and readable in your local browser.",
                ],
            )


def _extract_image_urls(page_html: str) -> list[str]:
    urls = []
    seen = set()
    patterns = [
        r'<img[^>]+(?:data-src|src)="([^"]+)"',
        r'cdn_url_\d+_\d+\s*=\s*["\'](https?://mmbiz[^"\']+)',
        r'msg_cdn_url\s*=\s*["\'](https?://mmbiz[^"\']+)',
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, page_html):
            image_url = html.unescape(match.group(1))
            if image_url.startswith("http") and image_url not in seen:
                seen.add(image_url)
                urls.append(image_url)
    return urls


def _external_wechat_markdown(url: str, timeout_seconds: float) -> str:
    command = os.environ.get("EASYSOURCEFLOW_WECHAT_MARKDOWN_COMMAND", "").strip()
    if not command:
        return ""
    args = [part.format(url=url) for part in shlex.split(command)]
    if "{url}" not in command:
        args.append(url)
    try:
        completed = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except Exception:
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def _external_wechat_document(url: str, settings: Settings) -> Optional[SourceDocument]:
    markdown = _external_wechat_markdown(url, settings.request_timeout_seconds)
    text = _normalize_lines(_strip_html(markdown))
    if len(text) < 80:
        return None
    title = _title_from_markdown(markdown) or url
    if len(text) > settings.max_content_chars:
        text = text[: settings.max_content_chars].rsplit("\n", 1)[0]
    return SourceDocument(
        source_url=url,
        canonical_url=url,
        source_type="wechat",
        title=title,
        author=None,
        published_at=None,
        language="zh",
        content_text=text,
        content_markdown=markdown[: settings.max_content_chars],
        metadata={},
        extraction_method="wechat_external_markdown",
    )


def _fallback_wechat_document(url: str, settings: Settings) -> Optional[SourceDocument]:
    external = _external_wechat_document(url, settings)
    if external:
        return external
    return _browser_wechat_document(url, settings)


def _browser_wechat_document(url: str, settings: Settings) -> Optional[SourceDocument]:
    page = None
    try:
        with _BROWSER_LOCK:
            browser = _get_browser()
            if not browser:
                return None
            page = browser.new_page(user_agent=WECHAT_UA)
            page.goto(url, wait_until="domcontentloaded", timeout=int(settings.request_timeout_seconds * 1000))
            try:
                page.wait_for_selector("#js_content, .rich_media_content, article", timeout=2500)
            except Exception:
                page.wait_for_timeout(1200)
            page_html = page.content()
    except Exception:
        _reset_browser_pool()
        return None
    finally:
        if page:
            try:
                page.close()
            except Exception:
                pass

    try:
        _raise_for_wechat_block_page(page_html)
    except Exception:
        return None
    title, author, published_at, text = _extract_wechat_fields(page_html)
    if len(text) < 80:
        return None
    if len(text) > settings.max_content_chars:
        text = text[: settings.max_content_chars].rsplit("\n", 1)[0]
    return SourceDocument(
        source_url=url,
        canonical_url=url,
        source_type="wechat",
        title=title or url,
        author=author,
        published_at=published_at,
        language="zh",
        content_text=text,
        content_markdown=text,
        metadata={"image_urls": _extract_image_urls(page_html), "browser_fallback": True},
        extraction_method="wechat_browser_playwright",
    )


def _title_from_markdown(markdown: str) -> str:
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""


def _get_browser():
    global _PLAYWRIGHT, _BROWSER
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None
    if _BROWSER:
        try:
            if _BROWSER.is_connected():
                return _BROWSER
        except Exception:
            _BROWSER = None
    if not _PLAYWRIGHT:
        _PLAYWRIGHT = sync_playwright().start()
    chrome_path = Path(os.environ.get("EASYSOURCEFLOW_CHROME_PATH", "")).expanduser()
    if not chrome_path.exists():
        chrome_path = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if chrome_path.exists():
        _BROWSER = _PLAYWRIGHT.chromium.launch(headless=True, executable_path=str(chrome_path))
    else:
        _BROWSER = _PLAYWRIGHT.chromium.launch(headless=True)
    return _BROWSER


def _reset_browser_pool() -> None:
    global _PLAYWRIGHT, _BROWSER
    try:
        if _BROWSER:
            _BROWSER.close()
    except Exception:
        pass
    _BROWSER = None
    try:
        if _PLAYWRIGHT:
            _PLAYWRIGHT.stop()
    except Exception:
        pass
    _PLAYWRIGHT = None


atexit.register(_reset_browser_pool)
