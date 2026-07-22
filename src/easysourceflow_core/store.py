"""SQLite-backed job store."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, List, Optional
from urllib.parse import quote


logger = logging.getLogger(__name__)
LATEST_SCHEMA_VERSION = 3


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class JobStore:
    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.database_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            logger.exception("sqlite operation failed: %s", self.database_path)
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            current = int(conn.execute("PRAGMA user_version").fetchone()[0])
            for version in range(current + 1, LATEST_SCHEMA_VERSION + 1):
                _apply_migration(conn, version)
                conn.execute(f"PRAGMA user_version = {version}")
                logger.info("applied sqlite migration version=%s database=%s", version, self.database_path)

    def schema_version(self) -> int:
        with self.connect() as conn:
            return int(conn.execute("PRAGMA user_version").fetchone()[0])

    def index_output(self, output_dir: Path, output_path: Path) -> None:
        root = output_dir.expanduser().resolve()
        path = output_path.expanduser().resolve()
        try:
            relative_path = path.relative_to(root).as_posix()
        except ValueError:
            return
        if not _is_searchable_output(relative_path, path):
            return
        try:
            stat = path.stat()
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        self._upsert_output_document(relative_path, content, stat.st_mtime, stat.st_size)

    def sync_output_index(self, output_dir: Path) -> dict:
        root = output_dir.expanduser().resolve()
        if not root.exists():
            return {"indexed": 0, "removed": 0, "fts": self._fts_available()}
        with self.connect() as conn:
            existing = {
                row["relative_path"]: (float(row["mtime"]), int(row["size"]))
                for row in conn.execute("SELECT relative_path, mtime, size FROM output_documents").fetchall()
            }
        seen = set()
        indexed = 0
        for path in root.rglob("*.md"):
            try:
                relative_path = path.resolve().relative_to(root).as_posix()
            except (OSError, ValueError):
                continue
            if not _is_searchable_output(relative_path, path):
                continue
            seen.add(relative_path)
            try:
                stat = path.stat()
            except OSError:
                continue
            previous = existing.get(relative_path)
            if previous and previous == (stat.st_mtime, stat.st_size):
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            self._upsert_output_document(relative_path, content, stat.st_mtime, stat.st_size)
            indexed += 1

        removed_paths = sorted(set(existing) - seen)
        if removed_paths:
            with self.connect() as conn:
                conn.executemany("DELETE FROM output_documents WHERE relative_path = ?", [(path,) for path in removed_paths])
                if _fts_available(conn):
                    conn.executemany("DELETE FROM output_documents_fts WHERE relative_path = ?", [(path,) for path in removed_paths])
        return {"indexed": indexed, "removed": len(removed_paths), "fts": self._fts_available()}

    def search_outputs(self, output_dir: Path, query: str, source_type: str = "", limit: int = 50) -> dict:
        root = output_dir.expanduser().resolve()
        sync = self.sync_output_index(root)
        q = query.strip()
        if not q:
            return {"items": [], "count": 0, "query": query, "index": sync}
        limit = max(1, min(limit, 100))
        rows = self._search_output_rows(q, source_type, limit)
        items = []
        for row in rows:
            data = dict(row)
            relative_path = data["relative_path"]
            path = root / relative_path
            parts = relative_path.split("/")
            content = data.get("content") or ""
            items.append(
                {
                    "title": data.get("title") or path.stem,
                    "date": parts[0] if parts else "",
                    "relative_path": relative_path,
                    "output_markdown_path": str(path.resolve()),
                    "source_type": data.get("source_type") or "output",
                    "size": int(data.get("size") or 0),
                    "updated_at": data.get("updated_at"),
                    "view_url": "/outputs/" + quote(relative_path),
                    "is_favorite": (root / "favorites" / relative_path).exists(),
                    "snippet": _search_snippet(content, q),
                }
            )
        return {"items": items, "count": len(items), "query": query, "index": sync}

    def create_job(
        self,
        job_id: str,
        url: str,
        instruction: str,
        request_kind: str = "link",
        summary_quality: str = "fast",
        request_payload: Optional[dict] = None,
        force_refresh: bool = False,
    ) -> dict:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    job_id, url, instruction, status, stage, progress, request_kind,
                    summary_quality, request_payload_json, force_refresh, created_at, updated_at
                ) VALUES (?, ?, ?, 'queued', 'received', 0, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    url,
                    instruction,
                    request_kind,
                    summary_quality,
                    json.dumps(request_payload or {}, ensure_ascii=False),
                    int(force_refresh),
                    now,
                    now,
                ),
            )
        return self.get_job(job_id)

    def mark_running(self, job_id: str, stage: str, progress: float) -> None:
        self._update(job_id, status="running", stage=stage, progress=progress)

    def update_summary_quality(self, job_id: str, summary_quality: str) -> None:
        self._update(job_id, summary_quality=summary_quality)

    def mark_succeeded(self, job_id: str, canonical_url: str, title: str, result: dict) -> None:
        result_json = json.dumps(result, ensure_ascii=False)
        self._update(
            job_id,
            canonical_url=canonical_url,
            status="succeeded",
            stage="done",
            progress=1.0,
            title=title,
            result_json=result_json,
            error_code=None,
            error_message=None,
        )

    def get_cached_result(
        self,
        canonical_url: str,
        instruction: str,
        summary_quality: str = "fast",
        cache_context: str = "",
        max_age_seconds: int = 604800,
    ) -> Optional[dict]:
        if max_age_seconds <= 0:
            return None
        cache_key = _cache_key(canonical_url, instruction, summary_quality, cache_context)
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM result_cache WHERE cache_key = ?", (cache_key,)).fetchone()
        if not row:
            return None
        data = dict(row)
        try:
            updated_at = datetime.fromisoformat(data["updated_at"])
            age_seconds = (datetime.now(timezone.utc) - updated_at).total_seconds()
        except (TypeError, ValueError):
            return None
        if age_seconds > max_age_seconds:
            return None
        try:
            result = json.loads(data["result_json"])
        except (TypeError, json.JSONDecodeError):
            self._delete_cached_result(cache_key)
            return None
        output_path = Path(str(result.get("output_markdown_path") or "")).expanduser()
        package_value = str(result.get("resource_package_path") or "")
        package_path = Path(package_value).expanduser() if package_value else None
        if not output_path.is_file() or (package_path is not None and not package_path.is_dir()):
            self._delete_cached_result(cache_key)
            return None
        return {
            "canonical_url": data["canonical_url"],
            "title": data["title"] or "",
            "result": result,
        }

    def put_cached_result(
        self,
        canonical_url: str,
        instruction: str,
        title: str,
        result: dict,
        summary_quality: str = "fast",
        cache_context: str = "",
    ) -> None:
        now = utc_now()
        cache_key = _cache_key(canonical_url, instruction, summary_quality, cache_context)
        result_json = json.dumps(result, ensure_ascii=False)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO result_cache (
                    cache_key, canonical_url, instruction, title, result_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    title = excluded.title,
                    result_json = excluded.result_json,
                    updated_at = excluded.updated_at
                """,
                (cache_key, canonical_url, instruction, title, result_json, now, now),
            )

    def mark_succeeded_from_cache(self, job_id: str, cached: dict, canonical_url: str = "") -> None:
        result = dict(cached["result"])
        result["cache_hit"] = True
        self.mark_succeeded(
            job_id=job_id,
            canonical_url=canonical_url or cached["canonical_url"],
            title=cached["title"],
            result=result,
        )

    def _delete_cached_result(self, cache_key: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM result_cache WHERE cache_key = ?", (cache_key,))

    def mark_failed(self, job_id: str, code: str, message: str, next_steps: Optional[List[str]] = None) -> None:
        self._update(
            job_id,
            status="failed",
            stage="failed",
            error_code=code,
            error_message=message,
            error_next_steps_json=json.dumps(next_steps or _default_next_steps(code), ensure_ascii=False),
        )

    def mark_canceled(self, job_id: str, message: str = "Job was canceled by the user.") -> None:
        self._update(
            job_id,
            status="canceled",
            stage="canceled",
            progress=0,
            error_code="canceled",
            error_message=message,
            error_next_steps_json=json.dumps(["Submit the same link or document again if you still need the result."], ensure_ascii=False),
            allow_canceled=True,
        )

    def is_canceled(self, job_id: str) -> bool:
        job = self.get_job(job_id)
        return bool(job and job.get("status") == "canceled")

    def status_counts(self, request_kind: Optional[str] = None, exclude_request_kind: Optional[str] = None) -> dict:
        with self.connect() as conn:
            if request_kind:
                rows = conn.execute(
                    "SELECT status, COUNT(*) AS count FROM jobs WHERE request_kind = ? GROUP BY status",
                    (request_kind,),
                ).fetchall()
            elif exclude_request_kind:
                rows = conn.execute(
                    "SELECT status, COUNT(*) AS count FROM jobs WHERE request_kind != ? GROUP BY status",
                    (exclude_request_kind,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT status, COUNT(*) AS count FROM jobs GROUP BY status").fetchall()
        return {row["status"]: row["count"] for row in rows}

    def prepare_recoverable_jobs(self) -> List[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status IN ('queued', 'running') ORDER BY created_at"
            ).fetchall()
            conn.execute(
                """
                UPDATE jobs
                SET status = 'queued', stage = 'recovered', progress = 0,
                    error_code = NULL, error_message = NULL, error_next_steps_json = NULL,
                    updated_at = ?
                WHERE status IN ('queued', 'running')
                """,
                (utc_now(),),
            )
        return [_row_to_dict(row) for row in rows]

    def mark_interrupted(self, job_id: str, message: str) -> None:
        now = utc_now()
        next_steps = json.dumps(["Retry this job from the Web console or MCP if you still need the result."], ensure_ascii=False)
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = 'failed',
                    stage = 'interrupted',
                    error_code = 'interrupted',
                    error_message = ?,
                    error_next_steps_json = ?,
                    updated_at = ?
                WHERE job_id = ? AND status IN ('queued', 'running')
                """,
                (message, next_steps, now, job_id),
            )

    def create_batch(self, batch_id: str, instruction: str, job_ids: List[str]) -> dict:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO batches (batch_id, instruction, job_ids_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (batch_id, instruction, json.dumps(job_ids), now, now),
            )
        return self.get_batch(batch_id) or {}

    def get_batch(self, batch_id: str) -> Optional[dict]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM batches WHERE batch_id = ?", (batch_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        job_ids = json.loads(data.pop("job_ids_json"))
        jobs = [self.get_job(job_id) for job_id in job_ids]
        items = [job for job in jobs if job]
        counts = {}
        for job in items:
            counts[job["status"]] = counts.get(job["status"], 0) + 1
        data["job_ids"] = job_ids
        data["items"] = items
        data["count"] = len(job_ids)
        data["status_counts"] = counts
        data["summary"] = _batch_summary(items)
        if counts.get("failed") and counts.get("failed") == len(job_ids):
            data["status"] = "failed"
        elif counts.get("succeeded") == len(job_ids):
            data["status"] = "succeeded"
        elif counts.get("failed") or counts.get("succeeded"):
            data["status"] = "partial"
        else:
            data["status"] = "running"
        return data

    def list_batches(self, limit: int = 20) -> List[dict]:
        limit = max(1, min(limit, 100))
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM batches ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        batches = []
        for row in rows:
            batch = self.get_batch(dict(row)["batch_id"])
            if batch:
                batches.append(batch)
        return batches

    def get_job(self, job_id: str) -> Optional[dict]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return _row_to_dict(row) if row else None

    def list_jobs(
        self,
        limit: int = 20,
        status: Optional[str] = None,
        request_kind: Optional[str] = None,
        exclude_request_kind: Optional[str] = None,
    ) -> List[dict]:
        limit = max(1, min(limit, 100))
        with self.connect() as conn:
            if status and request_kind:
                rows = conn.execute(
                    "SELECT * FROM jobs WHERE status = ? AND request_kind = ? ORDER BY created_at DESC LIMIT ?",
                    (status, request_kind, limit),
                ).fetchall()
            elif status and exclude_request_kind:
                rows = conn.execute(
                    "SELECT * FROM jobs WHERE status = ? AND request_kind != ? ORDER BY created_at DESC LIMIT ?",
                    (status, exclude_request_kind, limit),
                ).fetchall()
            elif request_kind:
                rows = conn.execute(
                    "SELECT * FROM jobs WHERE request_kind = ? ORDER BY created_at DESC LIMIT ?",
                    (request_kind, limit),
                ).fetchall()
            elif exclude_request_kind:
                rows = conn.execute(
                    "SELECT * FROM jobs WHERE request_kind != ? ORDER BY created_at DESC LIMIT ?",
                    (exclude_request_kind, limit),
                ).fetchall()
            elif status:
                rows = conn.execute(
                    "SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def _update(self, job_id: str, **fields: object) -> None:
        allow_canceled = bool(fields.pop("allow_canceled", False))
        fields["updated_at"] = utc_now()
        names = list(fields.keys())
        values = [fields[name] for name in names]
        assignments = ", ".join(f"{name} = ?" for name in names)
        condition = "job_id = ?" if allow_canceled else "job_id = ? AND status != 'canceled'"
        with self.connect() as conn:
            conn.execute(
                f"UPDATE jobs SET {assignments} WHERE {condition}",
                (*values, job_id),
            )

    def _upsert_output_document(self, relative_path: str, content: str, mtime: float, size: int) -> None:
        parts = relative_path.split("/")
        source_type = parts[1] if len(parts) > 2 else "output"
        title = _markdown_title(content) or Path(relative_path).stem
        search_text = _search_text(f"{title}\n{relative_path}\n{content}")
        updated_at = datetime.fromtimestamp(mtime, timezone.utc).isoformat(timespec="seconds")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO output_documents (
                    relative_path, title, source_type, content, search_text, mtime, size, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(relative_path) DO UPDATE SET
                    title = excluded.title,
                    source_type = excluded.source_type,
                    content = excluded.content,
                    search_text = excluded.search_text,
                    mtime = excluded.mtime,
                    size = excluded.size,
                    updated_at = excluded.updated_at
                """,
                (relative_path, title, source_type, content, search_text, mtime, size, updated_at),
            )
            if _fts_available(conn):
                conn.execute("DELETE FROM output_documents_fts WHERE relative_path = ?", (relative_path,))
                conn.execute(
                    "INSERT INTO output_documents_fts (relative_path, search_text) VALUES (?, ?)",
                    (relative_path, search_text),
                )

    def _search_output_rows(self, query: str, source_type: str, limit: int) -> List[sqlite3.Row]:
        with self.connect() as conn:
            if _fts_available(conn):
                sql = (
                    "SELECT d.* FROM output_documents_fts f "
                    "JOIN output_documents d ON d.relative_path = f.relative_path "
                    "WHERE output_documents_fts MATCH ?"
                )
                values: list[object] = [_fts_query(query)]
                if source_type:
                    sql += " AND d.source_type = ?"
                    values.append(source_type)
                sql += " ORDER BY d.mtime DESC LIMIT ?"
                values.append(limit)
                try:
                    return conn.execute(sql, values).fetchall()
                except sqlite3.OperationalError:
                    logger.exception("fts query failed; using indexed LIKE fallback")
            sql = "SELECT * FROM output_documents WHERE search_text LIKE ?"
            values = [f"%{_search_text(query)}%"]
            if source_type:
                sql += " AND source_type = ?"
                values.append(source_type)
            sql += " ORDER BY mtime DESC LIMIT ?"
            values.append(limit)
            return conn.execute(sql, values).fetchall()

    def _fts_available(self) -> bool:
        with self.connect() as conn:
            return _fts_available(conn)


def _row_to_dict(row: sqlite3.Row) -> dict:
    data = dict(row)
    if data.get("result_json"):
        data["result"] = json.loads(data["result_json"])
    else:
        data["result"] = None
    if data.get("error_next_steps_json"):
        data["error_next_steps"] = json.loads(data["error_next_steps_json"])
    elif data.get("error_code"):
        data["error_next_steps"] = _default_next_steps(data["error_code"])
    else:
        data["error_next_steps"] = []
    data.pop("result_json", None)
    data.pop("error_next_steps_json", None)
    if data.get("request_payload_json"):
        try:
            data["request_payload"] = json.loads(data["request_payload_json"])
        except json.JSONDecodeError:
            data["request_payload"] = {}
    else:
        data["request_payload"] = {}
    data["force_refresh"] = bool(data.get("force_refresh"))
    data.pop("request_payload_json", None)
    return data


def _cache_key(canonical_url: str, instruction: str, summary_quality: str = "fast", cache_context: str = "") -> str:
    quality = summary_quality if summary_quality in {"fast", "pro"} else "fast"
    return f"{canonical_url}\n{instruction.strip()}\nquality={quality}\ncontext={cache_context}"


def _apply_migration(conn: sqlite3.Connection, version: int) -> None:
    if version == 1:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                canonical_url TEXT,
                instruction TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                stage TEXT NOT NULL,
                progress REAL NOT NULL DEFAULT 0,
                title TEXT,
                result_json TEXT,
                error_code TEXT,
                error_message TEXT,
                error_next_steps_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        if "error_next_steps_json" not in columns:
            conn.execute("ALTER TABLE jobs ADD COLUMN error_next_steps_json TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS result_cache (
                cache_key TEXT PRIMARY KEY,
                canonical_url TEXT NOT NULL,
                instruction TEXT NOT NULL DEFAULT '',
                title TEXT,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_url ON result_cache(canonical_url)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS batches (
                batch_id TEXT PRIMARY KEY,
                instruction TEXT NOT NULL DEFAULT '',
                job_ids_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        return
    if version == 2:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        additions = {
            "request_kind": "TEXT NOT NULL DEFAULT 'link'",
            "summary_quality": "TEXT NOT NULL DEFAULT 'fast'",
            "request_payload_json": "TEXT",
            "force_refresh": "INTEGER NOT NULL DEFAULT 0",
        }
        for name, definition in additions.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")
        return
    if version == 3:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS output_documents (
                relative_path TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                source_type TEXT NOT NULL,
                content TEXT NOT NULL,
                search_text TEXT NOT NULL,
                mtime REAL NOT NULL,
                size INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_output_documents_source ON output_documents(source_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_output_documents_mtime ON output_documents(mtime DESC)")
        try:
            conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS output_documents_fts USING fts5(relative_path UNINDEXED, search_text)"
            )
        except sqlite3.OperationalError:
            logger.warning("SQLite FTS5 is unavailable; output search will use the indexed document table")
        return
    raise RuntimeError(f"Unknown SQLite schema migration: {version}")


def _fts_available(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'output_documents_fts'"
    ).fetchone()
    return bool(row)


def _is_searchable_output(relative_path: str, path: Path) -> bool:
    parts = relative_path.split("/")
    if not path.is_file() or not relative_path.endswith(".md"):
        return False
    if parts and parts[0] == "favorites":
        return False
    return path.name not in {"latest.md", "summary.md", "timeline.md"}


def _markdown_title(content: str) -> str:
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _search_text(value: str) -> str:
    chunks = []
    for match in re.finditer(r"[\u4e00-\u9fff]+|[A-Za-z0-9_]+", value.lower()):
        token = match.group(0)
        if "\u4e00" <= token[0] <= "\u9fff":
            chunks.extend(token)
        else:
            chunks.append(token)
    return " ".join(chunks)


def _fts_query(value: str) -> str:
    clauses = []
    for match in re.finditer(r"[\u4e00-\u9fff]+|[A-Za-z0-9_]+", value.lower()):
        token = match.group(0)
        normalized = " ".join(token) if "\u4e00" <= token[0] <= "\u9fff" else token
        clauses.append('"' + normalized.replace('"', '""') + '"')
    return " AND ".join(clauses) or '""'


def _search_snippet(content: str, query: str, radius: int = 90) -> str:
    lowered = content.lower()
    index = lowered.find(query.lower())
    if index < 0:
        return content[: radius * 2].strip()
    start = max(0, index - radius)
    end = min(len(content), index + len(query) + radius)
    prefix = "..." if start else ""
    suffix = "..." if end < len(content) else ""
    return prefix + content[start:end].strip() + suffix


def _batch_summary(items: List[dict]) -> dict:
    successes = []
    failures = []
    running = []
    for job in items:
        entry = {
            "job_id": job["job_id"],
            "url": job["url"],
            "title": job.get("title"),
            "status": job["status"],
            "stage": job["stage"],
        }
        result = job.get("result") or {}
        if result.get("output_markdown_path"):
            entry["output_markdown_path"] = result["output_markdown_path"]
        if result.get("resource_package_path"):
            entry["resource_package_path"] = result["resource_package_path"]
        if job["status"] == "succeeded":
            successes.append(entry)
        elif job["status"] == "failed":
            entry["error_code"] = job.get("error_code")
            entry["error_message"] = job.get("error_message")
            entry["error_next_steps"] = job.get("error_next_steps") or _default_next_steps(job.get("error_code") or "")
            failures.append(entry)
        else:
            running.append(entry)
    return {
        "succeeded": successes,
        "failed": failures,
        "running": running,
    }


def _default_next_steps(code: str) -> List[str]:
    if code == "need_cookies":
        return [
            "确认该视频在浏览器中可以用当前账号访问。",
            "重新导出 B 站 cookies 文件，并确认 .env 中的 EASYSOURCEFLOW_BILIBILI_COOKIES_FILE 指向它。",
            "如果是风控，降低批量频率后重试。",
        ]
    if code == "dependency_missing":
        return [
            "运行 scripts/easysourceflow health 查看缺失依赖。",
            "安装缺失的 yt-dlp、ffmpeg、whisper-cli 或 Playwright/Chrome。",
            "如果依赖已安装在 Homebrew 路径下，重新运行 scripts/easysourceflow install-launchd 刷新 launchd 环境。",
        ]
    if code == "invalid_url":
        return ["换成完整的 http 或 https 链接。"]
    if code == "unsupported_document":
        return ["换成 txt、md、srt、vtt、html、docx、epub 或 pdf 文件。"]
    if code == "invalid_document":
        return ["确认文件没有损坏，并重新选择文件提交。"]
    if code == "canceled":
        return ["如仍需要结果，重新提交相同链接或文件。"]
    if code == "interrupted":
        return ["服务重启前任务未完成；如仍需要结果，请重试该任务。"]
    if code == "extraction_failed":
        return [
            "在浏览器里打开链接，确认页面不需要登录且正文可见。",
            "微信公众号文章可稍后重试，或换公开可访问链接。",
            "如果网页阻止抓取，先手动提供正文。",
        ]
    return [
        "查看任务详情和日志。",
        "运行 scripts/easysourceflow health 确认依赖状态。",
        "用同一链接重试一次，确认是否为临时网络或平台问题。",
    ]
