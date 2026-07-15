"""Maintenance helpers for backup and log rotation."""

from __future__ import annotations

import argparse
import gzip
import json
import shutil
from datetime import datetime
from pathlib import Path

from .backup import backup_artifacts
from .config import Settings, load_settings
from .notifications import notify_event


def rotate_log(log_path: Path, max_bytes: int = 5_000_000, keep: int = 5) -> dict:
    log_path = log_path.expanduser()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if not log_path.exists():
        log_path.touch()
        return {"rotated": False, "log": str(log_path), "reason": "created"}
    size = log_path.stat().st_size
    if size < max_bytes:
        return {"rotated": False, "log": str(log_path), "bytes": size, "reason": "below_limit"}

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = log_path.with_name(f"{log_path.name}.{stamp}.gz")
    with log_path.open("rb") as source, gzip.open(archive, "wb") as target:
        shutil.copyfileobj(source, target)
    log_path.write_text("", encoding="utf-8")

    rotations = sorted(log_path.parent.glob(f"{log_path.name}.*.gz"), key=lambda path: path.stat().st_mtime, reverse=True)
    removed = []
    for old in rotations[keep:]:
        old.unlink(missing_ok=True)
        removed.append(str(old))
    return {"rotated": True, "log": str(log_path), "archive": str(archive), "bytes": size, "removed": removed}


def run_maintenance(log_path: Path, max_log_bytes: int = 5_000_000, keep_logs: int = 5) -> dict:
    settings = load_settings()
    try:
        backup = backup_artifacts(settings)
        log_rotation = rotate_log(log_path, max_bytes=max_log_bytes, keep=keep_logs)
        result = {
            "ok": True,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "backup": backup,
            "log_rotation": log_rotation,
        }
    except Exception as exc:
        result = {
            "ok": False,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    _write_maintenance_status(settings, result)
    notify_event(
        settings,
        "maintenance.succeeded" if result.get("ok") else "maintenance.failed",
        {"maintenance_status": "ok" if result.get("ok") else "failed", "error_message": result.get("error_message")},
    )
    return result


def maintenance_status(settings: Settings) -> dict:
    path = _maintenance_status_path(settings)
    if not path.exists():
        return {"ok": True, "status": "never_run", "path": str(path), "message": "Maintenance has not run yet."}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "status": "unreadable",
            "path": str(path),
            "message": f"Maintenance status cannot be read: {type(exc).__name__}.",
        }
    data["path"] = str(path)
    data["status"] = "ok" if data.get("ok") else "failed"
    return data


def _write_maintenance_status(settings: Settings, result: dict) -> None:
    path = _maintenance_status_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def _maintenance_status_path(settings: Settings) -> Path:
    return settings.data_dir / "maintenance-status.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run EasySourceFlow backup and log rotation.")
    parser.add_argument("--log", default=str(Path(__file__).resolve().parents[2] / "var" / "log" / "easysourceflowd.log"))
    parser.add_argument("--max-log-bytes", type=int, default=5_000_000)
    parser.add_argument("--keep-logs", type=int, default=5)
    parser.add_argument("--rotate-only", action="store_true")
    args = parser.parse_args()
    if args.rotate_only:
        result = rotate_log(Path(args.log), max_bytes=args.max_log_bytes, keep=args.keep_logs)
    else:
        result = run_maintenance(Path(args.log), max_log_bytes=args.max_log_bytes, keep_logs=args.keep_logs)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result.get("ok", True):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
