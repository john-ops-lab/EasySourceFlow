"""Public web article extraction."""

from __future__ import annotations

import html
import json
import logging
import re
from typing import Optional, Tuple
from urllib.request import Request, urlopen

from easysourceflow_core.config import Settings
from easysourceflow_core.errors import extraction_failed
from easysourceflow_core.models import SourceDocument
from easysourceflow_core.url_utils import detect_source_type, normalize_url


logger = logging.getLogger(__name__)


def extract_web_document(url: str, settings: Settings) -> SourceDocument:
    canonical_url = normalize_url(url, settings.allow_local_urls)
    page_html = ""
    title = author = published_at = ""
    metadata = {}
    try:
        page_html = _fetch_html(canonical_url, settings.request_timeout_seconds)
        title, author, published_at, text, metadata = _extract_article_fields(page_html)
    except Exception as exc:
        primary_error = type(exc).__name__
        primary_message = str(exc)
        fallback = _fetch_jina_reader_safe(canonical_url, settings.request_timeout_seconds, exc)
        if not fallback:
            raise
        title, author, published_at, text, metadata = fallback
        metadata["primary_fetch_error"] = primary_error
        if primary_message:
            metadata["primary_fetch_message"] = primary_message

    if len(text) < 80:
        fallback = _fetch_jina_reader_safe(canonical_url, settings.request_timeout_seconds, None)
        if fallback:
            title, author, published_at, text, metadata = fallback
        if len(text) < 80:
            raise extraction_failed("The page did not contain enough readable article text.")

    if len(text) > settings.max_content_chars:
        text = text[: settings.max_content_chars].rsplit(" ", 1)[0]

    return SourceDocument(
        source_url=url,
        canonical_url=canonical_url,
        source_type=detect_source_type(canonical_url),
        title=title or canonical_url,
        author=author,
        published_at=published_at,
        language=None,
        content_text=text,
        content_markdown=_text_to_markdown(text),
        metadata=metadata,
        extraction_method=metadata.get("extraction_method") or "html_metadata_readability",
    )


def _fetch_html(url: str, timeout_seconds: float) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type and "application/xhtml" not in content_type:
                raise extraction_failed(f"Unsupported content type: {content_type or 'unknown'}.")
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except Exception as exc:
        if getattr(exc, "code", None):
            raise extraction_failed(f"Could not fetch page; HTTP status {exc.code}.") from exc
        if exc.__class__.__name__ == "EasySourceFlowError":
            raise
        raise extraction_failed(f"Could not fetch page: {type(exc).__name__}.") from exc


def _extract_article_fields(page_html: str) -> Tuple[str, Optional[str], Optional[str], str, dict]:
    try:
        from bs4 import BeautifulSoup
    except Exception:
        title, text = _fallback_extract(page_html)
        return title, None, None, text, {}

    soup = BeautifulSoup(page_html, "html.parser")
    json_ld = _json_ld_metadata(soup)
    for tag in soup(["script", "style", "noscript", "svg", "canvas", "form", "nav", "footer", "aside", "header"]):
        tag.decompose()
    for selector in [
        "[class*=cookie]",
        "[class*=subscribe]",
        "[class*=newsletter]",
        "[class*=advert]",
        "[id*=cookie]",
        "[id*=comment]",
    ]:
        for node in soup.select(selector):
            node.decompose()

    title = _meta(soup, "property", "og:title") or _meta(soup, "name", "twitter:title")
    if soup.title and soup.title.string:
        title = title or _clean_text(soup.title.string)
    h1 = soup.find("h1")
    if h1:
        title = _clean_text(h1.get_text(" ", strip=True)) or title
    title = str(json_ld.get("headline") or title)
    author = _author_from_json_ld(json_ld) or _meta(soup, "name", "author") or _meta(soup, "property", "article:author") or None
    published_at = (
        str(json_ld.get("datePublished") or "")
        or _meta(soup, "property", "article:published_time")
        or _meta(soup, "name", "date")
        or None
    )

    article_body = _article_body_from_json_ld(json_ld)
    candidates = []
    for selector in ["article", "main", "[role=main]", ".article", ".post", ".content", "body"]:
        node = soup.select_one(selector)
        if node:
            candidates.append(node)

    best_text = ""
    for node in candidates:
        parts = [_clean_text(item.get_text(" ", strip=True)) for item in node.find_all(["h1", "h2", "h3", "p", "li", "blockquote"])]
        text = "\n\n".join(part for part in parts if len(part) >= 20)
        if len(text) > len(best_text):
            best_text = text

    if article_body and len(article_body) > len(best_text):
        best_text = article_body

    if not best_text and soup.body:
        best_text = _clean_text(soup.body.get_text("\n", strip=True))

    metadata = {
        "og_description": _meta(soup, "property", "og:description"),
        "json_ld_type": json_ld.get("@type", ""),
    }
    return title, author, published_at, _normalize_blocks(best_text), metadata


def _fallback_extract(page_html: str) -> Tuple[str, str]:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", page_html, flags=re.I | re.S)
    title = _clean_text(html.unescape(title_match.group(1))) if title_match else ""
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", page_html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return title, _normalize_blocks(html.unescape(text))


def _normalize_blocks(text: str) -> str:
    lines = [_clean_text(line) for line in re.split(r"[\r\n]+", text)]
    return "\n\n".join(line for line in lines if line)


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def _text_to_markdown(text: str) -> str:
    return "\n\n".join(_clean_text(block) for block in text.split("\n\n") if _clean_text(block))


def _meta(soup: object, attr: str, value: str) -> str:
    node = soup.find("meta", {attr: value})
    return _clean_text(node.get("content", "")) if node else ""


def _json_ld_metadata(soup: object) -> dict:
    for node in soup.find_all("script", {"type": "application/ld+json"}):
        raw = node.string or node.get_text("", strip=True)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            graph = item.get("@graph")
            if isinstance(graph, list):
                for graph_item in graph:
                    if _looks_like_article(graph_item):
                        return graph_item
            if _looks_like_article(item):
                return item
    return {}


def _article_body_from_json_ld(data: dict) -> str:
    body = data.get("articleBody") or data.get("text")
    if isinstance(body, str):
        return _normalize_blocks(body)
    return ""


def _fetch_jina_reader(url: str, timeout_seconds: float) -> Optional[Tuple[str, Optional[str], Optional[str], str, dict]]:
    if not url.startswith(("http://", "https://")):
        return None
    # The Jina Reader public API accepts the shorter form; keep a fallback for
    # older deployments and mirrors that have differed on accepted URL shapes.
    candidates = [
        "https://r.jina.ai/http://" + url,
        "https://s.jina.ai/http://" + url,
    ]
    for candidate in candidates:
        request = Request(candidate, headers={"User-Agent": "EasySourceFlow/0.1"})
        try:
            with urlopen(request, timeout=min(max(timeout_seconds, 10), 30)) as response:
                text = response.read().decode("utf-8", errors="replace").strip()
        except Exception:
            continue
        if len(text) < 80:
            continue
        title = ""
        match = re.search(r"^Title:\s*(.+)$", text, flags=re.MULTILINE)
        if match:
            title = _clean_text(match.group(1))
        cleaned = re.sub(r"^Title:.*?(?:\n|$)", "", text, flags=re.MULTILINE).strip()
        return (
            title,
            None,
            None,
            _normalize_blocks(cleaned),
            {"extraction_method": "jina_reader_fallback", "fallback_url": candidate},
        )
    return None


def _fetch_jina_reader_safe(
    url: str,
    timeout_seconds: float,
    primary_error: Optional[Exception],
) -> Optional[Tuple[str, Optional[str], Optional[str], str, dict]]:
    try:
        return _fetch_jina_reader(url, timeout_seconds)
    except Exception as exc:
        logger.warning(
            "jina reader fallback failed url=%s primary_error=%s fallback_error=%s",
            url,
            type(primary_error).__name__ if primary_error else "",
            type(exc).__name__,
        )
        return None


def _looks_like_article(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    item_type = item.get("@type")
    if isinstance(item_type, list):
        types = {str(value).lower() for value in item_type}
    else:
        types = {str(item_type).lower()}
    return bool(types & {"article", "newsarticle", "blogposting", "report"})


def _author_from_json_ld(data: dict) -> Optional[str]:
    author = data.get("author")
    if isinstance(author, dict):
        return _clean_text(str(author.get("name") or ""))
    if isinstance(author, list) and author:
        first = author[0]
        if isinstance(first, dict):
            return _clean_text(str(first.get("name") or ""))
        return _clean_text(str(first))
    if author:
        return _clean_text(str(author))
    return None
