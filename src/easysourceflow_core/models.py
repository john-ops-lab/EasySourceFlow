"""Shared data models."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


@dataclass
class SourceDocument:
    source_url: str
    canonical_url: str
    source_type: str
    title: str
    author: Optional[str]
    published_at: Optional[str]
    language: Optional[str]
    content_text: str
    content_markdown: str
    metadata: Dict[str, Any]
    extraction_method: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SummaryResult:
    title: str
    summary_markdown: str
    tags: List[str]
    suggested_note_path: str
    save_recommendation: Dict[str, object]
    source: SourceDocument

    def to_dict(self) -> dict:
        data = asdict(self)
        data["source"] = self.source.to_dict()
        return data
