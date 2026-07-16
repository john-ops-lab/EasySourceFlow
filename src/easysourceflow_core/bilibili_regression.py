"""Opt-in regression runner for public video-platform samples."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from .asr_quality import evaluate_transcript


TERMINAL_STATUSES = {"succeeded", "failed", "canceled"}


def run_manifest(manifest_path: Path, base_url: str, timeout_seconds: int, force_refresh: bool = False) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    results = []
    for sample in manifest.get("samples") or []:
        results.append(_run_sample(sample, manifest_path.parent, base_url.rstrip("/"), timeout_seconds, force_refresh))
    return {
        "ok": bool(results) and all(result["ok"] for result in results),
        "sample_count": len(results),
        "results": results,
    }


def _run_sample(sample: dict, manifest_dir: Path, base_url: str, timeout_seconds: int, force_refresh: bool) -> dict:
    sample_id = str(sample.get("id") or "unnamed")
    submitted = _http_json(
        f"{base_url}/jobs",
        method="POST",
        payload={
            "url": str(sample.get("url") or ""),
            "instruction": str(sample.get("instruction") or "用中文总结，保留核心要点和时间轴。"),
            "summary_quality": "pro",
            "force_refresh": force_refresh,
        },
    )
    job_id = str(submitted.get("job_id") or "")
    deadline = time.monotonic() + timeout_seconds
    job = submitted
    while job.get("status") not in TERMINAL_STATUSES and time.monotonic() < deadline:
        time.sleep(2)
        job = _http_json(f"{base_url}/jobs/{job_id}")

    checks = []
    _check(checks, "terminal_status", job.get("status") in TERMINAL_STATUSES, str(job.get("status")))
    _check(checks, "succeeded", job.get("status") == "succeeded", str(job.get("error_message") or job.get("status")))
    result = job.get("result") or {}
    source = result.get("source") or {}
    metadata = source.get("metadata") or {}
    provenance = metadata.get("subtitle_provenance") or {}
    origin = str(metadata.get("transcript_origin") or "none")
    expected_origins = sample.get("expected_transcript_origins") or []
    if expected_origins:
        _check(checks, "transcript_origin", origin in expected_origins, f"actual={origin}")
    expected_subtitle_statuses = sample.get("expected_subtitle_statuses") or []
    subtitle_status = str(metadata.get("subtitle_status") or "")
    if expected_subtitle_statuses:
        _check(
            checks,
            "subtitle_status",
            subtitle_status in expected_subtitle_statuses,
            f"actual={subtitle_status}",
        )
    expected_subtitle_languages = sample.get("expected_subtitle_languages") or []
    subtitle_language = str(metadata.get("subtitle_language") or "")
    if expected_subtitle_languages:
        _check(
            checks,
            "subtitle_language",
            any(subtitle_language.lower().startswith(str(item).lower()) for item in expected_subtitle_languages),
            f"actual={subtitle_language}",
        )
    expected_bvid = str(sample.get("expected_bvid") or "")
    if expected_bvid:
        _check(checks, "bvid", str(provenance.get("bvid") or "") == expected_bvid, f"actual={provenance.get('bvid')}")
    maximum_duration_ratio = sample.get("maximum_duration_ratio")
    if maximum_duration_ratio is not None:
        duration_ratio = _float_or_none(provenance.get("duration_ratio"))
        _check(
            checks,
            "subtitle_duration_ratio",
            duration_ratio is not None and duration_ratio <= float(maximum_duration_ratio),
            f"actual={duration_ratio}",
        )
    summary = str(result.get("summary_markdown") or "")
    if sample.get("expected_summary_language") == "zh":
        _check(checks, "chinese_summary", _chinese_ratio(summary) >= 0.05, "summary must contain meaningful Chinese text")
    minimum_core_points = int(sample.get("minimum_core_points") or 0)
    if minimum_core_points:
        core_points = _section_item_count(summary, "核心要点")
        timeline_points = _section_item_count(summary, "核心要点时间轴")
        _check(checks, "core_points", core_points >= minimum_core_points, f"actual={core_points}")
        _check(checks, "timeline_matches_core_points", timeline_points == core_points, f"timeline={timeline_points}, core={core_points}")

    asr_evaluation = None
    reference_path = str(sample.get("reference_transcript") or "")
    transcript_path = str(result.get("resource_package_path") or "")
    if reference_path and transcript_path:
        reference = (manifest_dir / reference_path).resolve()
        hypothesis = Path(transcript_path) / "transcript_with_timestamps.txt"
        if reference.is_file() and hypothesis.is_file():
            asr_evaluation = evaluate_transcript(
                reference.read_text(encoding="utf-8", errors="replace"),
                hypothesis.read_text(encoding="utf-8", errors="replace"),
                duration_seconds=_float_or_none(metadata.get("duration")),
            )
            maximum_cer = float(sample.get("maximum_character_error_rate", 1.0))
            _check(checks, "asr_character_error_rate", asr_evaluation["character_error_rate"] <= maximum_cer, f"actual={asr_evaluation['character_error_rate']}")

    return {
        "id": sample_id,
        "job_id": job_id,
        "status": job.get("status"),
        "ok": bool(checks) and all(check["ok"] for check in checks),
        "checks": checks,
        "transcript_origin": origin,
        "transcript_quality": metadata.get("transcript_quality"),
        "asr_evaluation": asr_evaluation,
        "output_markdown_path": result.get("output_markdown_path"),
    }


def _http_json(url: str, method: str = "GET", payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(url, data=body, headers={"content-type": "application/json"}, method=method)
    with urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("EasySourceFlow returned a non-object JSON response.")
    return data


def _check(checks: list[dict], name: str, ok: bool, detail: str) -> None:
    checks.append({"name": name, "ok": bool(ok), "detail": detail})


def _section_item_count(markdown: str, heading: str) -> int:
    marker = f"## {heading}"
    if marker not in markdown:
        return 0
    section = markdown.split(marker, 1)[1].split("\n## ", 1)[0]
    return sum(1 for line in section.splitlines() if line.lstrip().startswith(("- ", "* ")) or line.lstrip()[:2].rstrip(".").isdigit())


def _chinese_ratio(value: str) -> float:
    non_space = [character for character in value if not character.isspace()]
    if not non_space:
        return 0.0
    chinese = sum("\u4e00" <= character <= "\u9fff" for character in non_space)
    return chinese / len(non_space)


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Run opt-in EasySourceFlow regressions against public video samples.")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--timeout", type=int, default=7200)
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = run_manifest(args.manifest, args.base_url, max(1, args.timeout), force_refresh=args.force_refresh)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
