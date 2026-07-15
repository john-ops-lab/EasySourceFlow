"""ASR transcript quality metrics with no external runtime dependency."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Optional


_TIMESTAMP = re.compile(r"^\[(?P<start>\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?)\s*(?:-|-->)?")


def evaluate_transcript(reference: str, hypothesis: str, duration_seconds: Optional[float] = None) -> dict:
    reference_text = _normalize_text(reference)
    hypothesis_text = _normalize_text(hypothesis)
    max_chars = 5000
    truncated = len(reference_text) > max_chars or len(hypothesis_text) > max_chars
    reference_sample = reference_text[:max_chars]
    hypothesis_sample = hypothesis_text[:max_chars]
    distance = _edit_distance(reference_sample, hypothesis_sample)
    cer = distance / max(1, len(reference_sample))
    timing = transcript_timing_quality(hypothesis, duration_seconds)
    return {
        "reference_chars": len(reference_text),
        "hypothesis_chars": len(hypothesis_text),
        "evaluated_chars": len(reference_sample),
        "truncated": truncated,
        "character_error_rate": round(cer, 4),
        "character_accuracy": round(max(0.0, 1.0 - cer), 4),
        "timing": timing,
        "grade": _grade(cer, timing),
    }


def transcript_timing_quality(transcript: str, duration_seconds: Optional[float] = None) -> dict:
    timestamps = []
    for raw_line in transcript.splitlines():
        match = _TIMESTAMP.match(raw_line.strip())
        if match:
            timestamps.append(_time_to_seconds(match.group("start")))
    monotonic = all(current >= previous for previous, current in zip(timestamps, timestamps[1:]))
    coverage = None
    if duration_seconds and duration_seconds > 0 and timestamps:
        coverage = min(1.0, max(0.0, timestamps[-1] / duration_seconds))
    return {
        "timestamp_count": len(timestamps),
        "timestamps_monotonic": monotonic,
        "duration_coverage": round(coverage, 4) if coverage is not None else None,
    }


def describe_transcript_quality(transcript: str, duration_seconds: Optional[float], origin: str) -> dict:
    plain = _normalize_text(transcript)
    timing = transcript_timing_quality(transcript, duration_seconds)
    if not plain:
        confidence = "none"
    elif origin == "platform_subtitle":
        confidence = "high"
    elif not timing["timestamps_monotonic"] or len(plain) < 80:
        confidence = "low"
    elif timing["duration_coverage"] is not None and timing["duration_coverage"] < 0.5:
        confidence = "low"
    else:
        confidence = "medium"
    return {
        "confidence": confidence,
        "character_count": len(plain),
        **timing,
    }


def _normalize_text(text: str) -> str:
    text = re.sub(r"^\[[^\]]+\]\s*", "", text, flags=re.M)
    text = re.sub(r"^\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?\s*-->.*$", "", text, flags=re.M)
    return "".join(character.lower() for character in text if character.isalnum())


def _edit_distance(left: str, right: str) -> int:
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for left_index, left_character in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_character in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_character != right_character),
                )
            )
        previous = current
    return previous[-1]


def _time_to_seconds(value: str) -> float:
    parts = value.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    return float(parts[0])


def _grade(cer: float, timing: dict) -> str:
    if not timing["timestamps_monotonic"]:
        return "poor"
    if cer <= 0.15:
        return "good"
    if cer <= 0.30:
        return "review"
    return "poor"


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate an ASR transcript against a reference transcript.")
    parser.add_argument("reference", type=Path)
    parser.add_argument("hypothesis", type=Path)
    parser.add_argument("--duration", type=float)
    args = parser.parse_args()
    result = evaluate_transcript(
        args.reference.read_text(encoding="utf-8", errors="replace"),
        args.hypothesis.read_text(encoding="utf-8", errors="replace"),
        duration_seconds=args.duration,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
