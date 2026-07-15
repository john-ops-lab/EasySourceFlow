"""Markdown output file writer."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import SummaryResult

_TIMELINE_LINK_PLACEHOLDER = "{{EASYSOURCEFLOW_TIMELINE_LINK}}"


def write_summary_markdown(result: SummaryResult, output_dir: Path) -> Path:
    output_dir = _target_dir(result, output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = _filename(result)
    path = _dedupe_path(output_dir / filename)
    content = _summary_content(result.summary_markdown, f"{path.stem}/timeline.md")
    path.write_text(content, encoding="utf-8")
    (output_dir / "latest.md").write_text(content, encoding="utf-8")
    return path


def write_resource_package(result: SummaryResult, summary_path: Path) -> Optional[Path]:
    package_dir = summary_path.with_suffix("")
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "summary.md").write_text(
        _summary_content(result.summary_markdown, "timeline.md"),
        encoding="utf-8",
    )
    source_metadata = result.source.metadata or {}
    if result.source.content_text:
        (package_dir / "source_content.txt").write_text(result.source.content_text.rstrip() + "\n", encoding="utf-8")
    if result.source.content_markdown and result.source.content_markdown != result.source.content_text:
        (package_dir / "source_markdown.md").write_text(result.source.content_markdown.rstrip() + "\n", encoding="utf-8")
    transcript_with_timestamps = str(source_metadata.get("transcript_with_timestamps") or _extract_transcript(result.source.content_text))
    transcript = str(source_metadata.get("transcript_text") or _strip_timestamps(transcript_with_timestamps))
    subtitle_vtt = str(source_metadata.get("subtitle_vtt") or "")
    if subtitle_vtt:
        (package_dir / "subtitle.vtt").write_text(subtitle_vtt.rstrip() + "\n", encoding="utf-8")
    if transcript_with_timestamps:
        (package_dir / "transcript_with_timestamps.txt").write_text(
            transcript_with_timestamps.rstrip() + "\n",
            encoding="utf-8",
        )
    if transcript:
        (package_dir / "transcript.txt").write_text(transcript.rstrip() + "\n", encoding="utf-8")
    timeline = _timeline_markdown(result.source.canonical_url, transcript_with_timestamps)
    if timeline:
        (package_dir / "timeline.md").write_text(timeline.rstrip() + "\n", encoding="utf-8")
    if source_metadata.get("raw_metadata"):
        (package_dir / "raw_metadata.json").write_text(
            json.dumps(source_metadata["raw_metadata"], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    metadata = {
        "title": result.source.title,
        "source_url": result.source.source_url,
        "canonical_url": result.source.canonical_url,
        "source_type": result.source.source_type,
        "author": result.source.author,
        "published_at": result.source.published_at,
        "language": result.source.language,
        "extraction_method": result.source.extraction_method,
        "metadata": result.source.metadata,
        "tags": result.tags,
    }
    (package_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    source_info = {
        "title": result.source.title,
        "url": result.source.canonical_url,
        "source_type": result.source.source_type,
        "author": result.source.author,
        "published_at": result.source.published_at,
        "extraction_method": result.source.extraction_method,
        "subtitle_status": source_metadata.get("subtitle_status"),
        "subtitle_source": source_metadata.get("subtitle_source"),
        "transcript_origin": source_metadata.get("transcript_origin"),
        "transcript_origin_label": source_metadata.get("transcript_origin_label"),
        "transcript_quality": source_metadata.get("transcript_quality"),
        "duration": source_metadata.get("duration"),
        "resource_files": sorted(path.name for path in package_dir.iterdir() if path.is_file()),
    }
    (package_dir / "source_info.json").write_text(
        json.dumps(source_info, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return package_dir


def _summary_content(markdown: str, timeline_link: str) -> str:
    content = markdown.rstrip().replace(_TIMELINE_LINK_PLACEHOLDER, timeline_link)
    return content + "\n"


def _target_dir(result: SummaryResult, output_dir: Path) -> Path:
    date = datetime.now().strftime("%Y-%m-%d")
    source_type = _safe_part(result.source.source_type or "source")
    return output_dir / date / source_type


def _filename(result: SummaryResult) -> str:
    slug = _safe_part(result.title)
    if not slug:
        slug = "untitled"
    if len(slug) > 90:
        slug = slug[:90].rstrip("-")
    timestamp = datetime.now().strftime("%H%M%S")
    return f"{timestamp}-{slug}.md"


def _safe_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]+", "-", value).strip("-").lower()


def _dedupe_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    for i in range(2, 1000):
        candidate = parent / f"{stem}-{i}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError("Could not find available summary output filename.")


def _extract_transcript(content_text: str) -> str:
    marker = "\n\nTranscript:\n\n"
    if marker not in content_text:
        return ""
    return content_text.split(marker, 1)[1].strip()


def _strip_timestamps(transcript: str) -> str:
    lines = []
    for line in transcript.splitlines():
        cleaned = re.sub(r"^\[[^\]]+\]\s*", "", line).strip()
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)


def _timeline_markdown(url: str, transcript: str) -> str:
    lines = ["# Timeline", ""]
    count = 0
    for raw in transcript.splitlines():
        match = re.match(r"^\[(?P<time>[^\]]+)\]\s*(?P<text>.+)$", raw.strip())
        if not match:
            continue
        text = re.sub(r"\s+", " ", match.group("text")).strip()
        if not text:
            continue
        start = match.group("time").split("-", 1)[0]
        link = _timestamp_link(url, _time_to_seconds(start))
        lines.append(f"- [{start}]({link}) {text}")
        count += 1
    return "\n".join(lines) if count else ""


def _time_to_seconds(value: str) -> int:
    parts = [part for part in re.split(r"[:.]", value) if part.isdigit()]
    if len(parts) >= 3:
        return int(parts[-3]) * 3600 + int(parts[-2]) * 60 + int(parts[-1])
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    if len(parts) == 1:
        return int(parts[0])
    return 0


def _timestamp_link(url: str, seconds: int) -> str:
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}t={max(0, seconds)}"
