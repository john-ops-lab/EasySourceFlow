"""Backup EasySourceFlow local data and outputs."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import tarfile
from datetime import datetime
from pathlib import Path

from .config import Settings, load_settings


def backup_artifacts(settings: Settings, backup_dir: Path | None = None) -> dict:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    root = (backup_dir or (settings.data_dir / "backups")).expanduser().resolve()
    target = root / f"easysourceflow-backup-{stamp}"
    target.mkdir(parents=True, exist_ok=False)

    copied = []
    if settings.database_path.exists():
        db_target = target / "easysourceflow.sqlite3"
        with sqlite3.connect(str(settings.database_path)) as source:
            with sqlite3.connect(str(db_target)) as dest:
                source.backup(dest)
        copied.append(str(db_target))

    if settings.output_dir.exists():
        archive_path = target / "output.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(settings.output_dir, arcname="output")
        copied.append(str(archive_path))

    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "database_path": str(settings.database_path),
        "output_dir": str(settings.output_dir),
        "backup_dir": str(target),
        "files": copied,
    }
    manifest_path = target / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    copied.append(str(manifest_path))

    latest = root / "latest"
    if latest.exists() or latest.is_symlink():
        if latest.is_dir() and not latest.is_symlink():
            shutil.rmtree(latest)
        else:
            latest.unlink()
    latest.symlink_to(target, target_is_directory=True)

    return {"ok": True, "backup_dir": str(target), "files": copied, "latest": str(latest)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Back up EasySourceFlow SQLite database and outputs.")
    parser.add_argument("--dir", dest="backup_dir", default="", help="Backup destination directory.")
    args = parser.parse_args()
    result = backup_artifacts(load_settings(), backup_dir=Path(args.backup_dir) if args.backup_dir else None)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
