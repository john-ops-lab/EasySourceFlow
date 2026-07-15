"""Cleanup old EasySourceFlow artifacts."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import time
from pathlib import Path

from .config import Settings, load_settings


def cleanup_artifacts(
    settings: Settings,
    days: int = 14,
    dry_run: bool = True,
    include_temp: bool = True,
    include_outputs: bool = True,
    include_jobs: bool = False,
) -> dict:
    result = {
        "dry_run": dry_run,
        "days": days,
        "removed": [],
        "kept_recent_count": 0,
        "categories": {
            "temp": [],
            "outputs": [],
            "jobs": [],
        },
    }
    if days <= 0 and not dry_run:
        result["ok"] = False
        result["error"] = {
            "code": "unsafe_cleanup_window",
            "message": "Refusing to delete artifacts with days <= 0.",
        }
        return result

    cutoff = time.time() - max(0, days) * 86400

    if include_temp:
        for root in [settings.data_dir / "downloads", settings.data_dir / "tmp"]:
            if not root.exists():
                continue
            for path in sorted(root.iterdir()):
                if not _is_old(path, cutoff):
                    result["kept_recent_count"] += 1
                    continue
                item = _remove(path, dry_run)
                result["categories"]["temp"].append(item)
                result["removed"].append(item)

    if include_outputs and settings.output_dir.exists():
        for date_dir in sorted(settings.output_dir.iterdir()):
            if not date_dir.is_dir() or not _is_old(date_dir, cutoff):
                continue
            item = _remove(date_dir, dry_run)
            result["categories"]["outputs"].append(item)
            result["removed"].append(item)

    if include_jobs:
        result["categories"]["jobs"] = _cleanup_jobs(settings.database_path, cutoff, dry_run)
        result["removed"].extend(result["categories"]["jobs"])

    return result


def _is_old(path: Path, cutoff: float) -> bool:
    try:
        return path.stat().st_mtime < cutoff
    except FileNotFoundError:
        return False


def _remove(path: Path, dry_run: bool) -> dict:
    item = {"path": str(path), "type": "dir" if path.is_dir() else "file"}
    if dry_run:
        item["removed"] = False
        return item
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)
    item["removed"] = True
    return item


def _cleanup_jobs(database_path: Path, cutoff: float, dry_run: bool) -> list[dict]:
    if not database_path.exists():
        return []
    cutoff_iso = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(cutoff))
    with sqlite3.connect(str(database_path)) as conn:
        rows = conn.execute(
            "SELECT job_id, status, updated_at FROM jobs WHERE updated_at < ? ORDER BY updated_at",
            (cutoff_iso,),
        ).fetchall()
        items = [{"job_id": row[0], "status": row[1], "updated_at": row[2], "removed": False} for row in rows]
        if not dry_run and rows:
            job_ids = [row[0] for row in rows]
            conn.executemany("DELETE FROM jobs WHERE job_id = ?", [(job_id,) for job_id in job_ids])
            for item in items:
                item["removed"] = True
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean old EasySourceFlow artifacts.")
    parser.add_argument("--days", type=int, default=14, help="Remove artifacts older than this many days.")
    parser.add_argument("--apply", action="store_true", help="Actually remove files. Default is dry-run.")
    parser.add_argument("--no-temp", action="store_true", help="Skip downloads and temporary files.")
    parser.add_argument("--no-outputs", action="store_true", help="Skip output Markdown/resource directories.")
    parser.add_argument("--jobs", action="store_true", help="Also remove old SQLite job records.")
    args = parser.parse_args()
    result = cleanup_artifacts(
        load_settings(),
        days=args.days,
        dry_run=not args.apply,
        include_temp=not args.no_temp,
        include_outputs=not args.no_outputs,
        include_jobs=args.jobs,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
