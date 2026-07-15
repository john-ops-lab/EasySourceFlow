"""Local document payload extraction."""

from __future__ import annotations

import base64
import re
import zipfile
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from typing import Tuple
from xml.etree import ElementTree

from .errors import EasySourceFlowError, dependency_missing


TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".srt", ".vtt", ".csv", ".json", ".xml", ".yaml", ".yml"}
HTML_SUFFIXES = {".html", ".htm"}


def document_payload_to_text(payload: dict) -> Tuple[str, str, dict]:
    """Return title, extracted text, and metadata for a browser-uploaded document."""

    title = str(payload.get("title") or payload.get("filename") or "local-document").strip()[:180] or "local-document"
    content = str(payload.get("content") or "")
    suffix = Path(title).suffix.lower()
    mime_type = str(payload.get("mime_type") or payload.get("mimeType") or "")

    if content:
        if suffix in HTML_SUFFIXES or "html" in mime_type:
            text = _html_to_text(content)
            return title, text, {"input_kind": "uploaded_html", "mime_type": mime_type}
        return title, content, {"input_kind": "uploaded_text", "mime_type": mime_type}

    data_base64 = str(payload.get("data_base64") or payload.get("dataBase64") or "")
    if not data_base64:
        return title, "", {"input_kind": "empty_upload", "mime_type": mime_type}

    try:
        raw = base64.b64decode(data_base64, validate=True)
    except Exception as exc:
        raise EasySourceFlowError(
            code="invalid_document",
            message="Uploaded document payload is not valid base64.",
            next_steps=["Choose the file again in the Web console and retry."],
        ) from exc

    if suffix in TEXT_SUFFIXES or mime_type.startswith("text/"):
        return title, _decode_text(raw), {"input_kind": "uploaded_text", "mime_type": mime_type}
    if suffix in HTML_SUFFIXES or "html" in mime_type:
        return title, _html_to_text(_decode_text(raw)), {"input_kind": "uploaded_html", "mime_type": mime_type}
    if suffix == ".docx":
        return title, _docx_to_text(raw), {"input_kind": "uploaded_docx", "mime_type": mime_type}
    if suffix == ".epub":
        return title, _epub_to_text(raw), {"input_kind": "uploaded_epub", "mime_type": mime_type}
    if suffix == ".pdf" or mime_type == "application/pdf":
        return title, _pdf_to_text(raw), {"input_kind": "uploaded_pdf", "mime_type": mime_type}

    raise EasySourceFlowError(
        code="unsupported_document",
        message=f"Unsupported local file type: {suffix or mime_type or 'unknown'}.",
        next_steps=["Use txt, md, srt, vtt, html, docx, epub, or pdf."],
    )


def _decode_text(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _html_to_text(markup: str) -> str:
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(markup, "html.parser")
        for node in soup(["script", "style", "noscript", "template"]):
            node.decompose()
        title = soup.find("title")
        body = soup.find("article") or soup.find("main") or soup.body or soup
        parts = []
        if title and title.get_text(strip=True):
            parts.append(title.get_text(" ", strip=True))
        text = body.get_text("\n", strip=True)
        if text:
            parts.append(text)
        return _clean_lines("\n".join(parts))
    except Exception:
        parser = _TextHTMLParser()
        parser.feed(markup)
        return _clean_lines("\n".join(parser.parts))


def _docx_to_text(raw: bytes) -> str:
    try:
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            names = ["word/document.xml"]
            names.extend(name for name in archive.namelist() if name.startswith("word/header") or name.startswith("word/footer"))
            parts = [_docx_xml_to_text(archive.read(name)) for name in names if name in archive.namelist()]
    except zipfile.BadZipFile as exc:
        raise EasySourceFlowError(
            code="invalid_document",
            message="The uploaded DOCX file is not a valid Word document.",
            next_steps=["Open the document locally and export it as .docx again, then retry."],
        ) from exc
    return _clean_lines("\n".join(part for part in parts if part))


def _docx_xml_to_text(raw_xml: bytes) -> str:
    root = ElementTree.fromstring(raw_xml)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = []
    for paragraph in root.findall(".//w:p", namespace):
        runs = [node.text or "" for node in paragraph.findall(".//w:t", namespace)]
        text = "".join(runs).strip()
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs)


def _epub_to_text(raw: bytes) -> str:
    try:
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            names = [
                name
                for name in archive.namelist()
                if name.lower().endswith((".html", ".xhtml", ".htm")) and "nav" not in Path(name).stem.lower()
            ]
            parts = [_html_to_text(_decode_text(archive.read(name))) for name in sorted(names)]
    except zipfile.BadZipFile as exc:
        raise EasySourceFlowError(
            code="invalid_document",
            message="The uploaded EPUB file is not a valid EPUB archive.",
            next_steps=["Open the book locally and export/download it again, then retry."],
        ) from exc
    return _clean_lines("\n\n".join(part for part in parts if part))


def _pdf_to_text(raw: bytes) -> str:
    try:
        from pypdf import PdfReader
    except Exception as exc:
        raise dependency_missing("pypdf is required to extract uploaded PDF text.") from exc
    reader = PdfReader(BytesIO(raw))
    pages = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(f"[Page {index}]\n{text.strip()}")
    return _clean_lines("\n\n".join(pages))


def _clean_lines(text: str) -> str:
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class _TextHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in {"script", "style", "noscript", "template"}:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "template"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text and not self._skip:
            self.parts.append(text)
