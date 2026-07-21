"""Minimal stdio MCP adapter for easysourceflowd."""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from easysourceflow_core import __version__
from easysourceflow_core.url_utils import detect_source_type


BASE_URL = os.environ.get("EASYSOURCEFLOW_BASE_URL", "http://127.0.0.1:8765").rstrip("/")
logger = logging.getLogger(__name__)
_CLIENT_HEADERS = {"x-easysourceflow-client": "mcp", "user-agent": f"EasySourceFlow-MCP/{__version__}"}


TOOLS = [
    {
        "name": "easysourceflow_summarize_link",
        "description": (
            "Compatibility tool for synchronously summarizing a short non-video webpage. Do not use this "
            "tool for Bilibili or YouTube; use easysourceflow_submit_link and then independently call "
            "easysourceflow_get_job. The tool returns final Markdown "
            "intended for direct delivery to the user; relay it verbatim unless the user explicitly asks you to rewrite it. "
            "For chat-card delivery, put the Markdown in the message tool's card.elements markdown content; "
            "do not send card JSON as plain message text."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Public http or https URL to summarize."},
                "instruction": {"type": "string", "description": "User summary instruction.", "default": ""},
                "summary_quality": {"type": "string", "enum": ["fast", "pro"], "description": "Use fast for the configured normal model, or pro for the configured strong model. Video links are automatically treated as pro.", "default": "fast"},
                "force_refresh": {"type": "boolean", "description": "Ignore cached results and fetch and summarize the source again.", "default": False},
            },
            "required": ["url"],
        },
    },
    {
        "name": "easysourceflow_submit_link",
        "description": (
            "Default entry point for every URL summarization request. Submit a public URL for durable background "
            "processing and retain the returned job ID. Then call easysourceflow_get_job with wait_seconds=45 until "
            "the job reaches succeeded, failed, or canceled. A queued or running response is not a failure and must "
            "never be replaced with an independent web fetch or summary."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Public http or https URL to process."},
                "instruction": {"type": "string", "description": "User summary instruction.", "default": ""},
                "summary_quality": {"type": "string", "enum": ["fast", "pro"], "description": "Use fast for the configured normal model, or pro for the configured strong model. Video links are automatically treated as pro.", "default": "fast"},
                "force_refresh": {"type": "boolean", "description": "Ignore cached results and fetch and summarize the source again.", "default": False},
            },
            "required": ["url"],
        },
    },
    {
        "name": "easysourceflow_get_job",
        "description": (
            "Independently query an EasySourceFlow job, optionally waiting up to 45 seconds for a state change. "
            "If status remains queued or running, call this tool again with the same job ID; do not fetch or summarize "
            "the source with another tool. Only status=succeeded with result.summary_markdown is a completed summary. "
            "If the job succeeded, the tool returns final Markdown "
            "intended for direct delivery to the user; relay it verbatim unless the user explicitly asks you to rewrite it. "
            "For chat-card delivery, put the Markdown in the message tool's card.elements markdown content; "
            "do not send card JSON as plain message text."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "Job ID returned by easysourceflow_submit_link."},
                "wait_seconds": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 45,
                    "default": 0,
                    "description": "Wait up to this many seconds while the job is queued or running. Use 45 for agent polling.",
                },
            },
            "required": ["job_id"],
        },
    },
    {
        "name": "easysourceflow_favorite_result",
        "description": (
            "Favorite an EasySourceFlow summary. If the user replies exactly '收藏' after you returned an "
            "EasySourceFlow summary, call this tool without arguments to favorite the most recent result. "
            "You can also pass job_id, output_markdown_path, or relative_path when available."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "Optional EasySourceFlow job ID whose result should be favorited."},
                "output_markdown_path": {"type": "string", "description": "Optional absolute output_markdown_path returned by EasySourceFlow."},
                "relative_path": {"type": "string", "description": "Optional output relative_path from /outputs."},
            },
        },
    },
    {
        "name": "easysourceflow_retry_job",
        "description": "Retry a previous EasySourceFlow job and return the new job.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "Existing job ID to retry."},
                "instruction": {"type": "string", "description": "Optional replacement instruction."},
                "summary_quality": {"type": "string", "enum": ["fast", "pro"], "description": "Optional replacement summary quality."},
                "force_refresh": {"type": "boolean", "description": "Ignore cache when retrying. Defaults to true.", "default": True},
            },
            "required": ["job_id"],
        },
    },
    {
        "name": "easysourceflow_cancel_job",
        "description": "Cancel a queued or running EasySourceFlow job. Running subprocess work may finish in the background, but the canceled job will not be overwritten.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "Existing job ID to cancel."}
            },
            "required": ["job_id"],
        },
    },
    {
        "name": "easysourceflow_submit_document",
        "description": (
            "Submit pasted text, Markdown, or complete content read by an authenticated document connector. "
            "For cloud documents, include the original source_url so EasySourceFlow preserves provenance and writes the result to the correct library source."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Document title or filename."},
                "content": {"type": "string", "description": "Plain text or Markdown content."},
                "source_url": {"type": "string", "description": "Original HTTPS URL for connector-read cloud documents, such as a Feishu Docs or Wiki link."},
                "instruction": {"type": "string", "description": "User summary instruction.", "default": ""},
                "summary_quality": {"type": "string", "enum": ["fast", "pro"], "description": "Use fast for the configured normal model, or pro for the configured strong model. Video links are automatically treated as pro.", "default": "fast"},
                "force_refresh": {"type": "boolean", "description": "Ignore cached results.", "default": False},
            },
            "required": ["content"],
        },
    },
    {
        "name": "easysourceflow_submit_document_file",
        "description": (
            "Submit the original bytes of a user-uploaded document. Use this for PDF attachments even when the chat "
            "contains preview text, because previews may be truncated. The file must be inside an approved Agent upload "
            "directory; arbitrary local paths are rejected. Retain the returned job ID and poll easysourceflow_get_job."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Platform-provided path to the uploaded attachment."},
                "title": {"type": "string", "description": "Original attachment filename shown to the user."},
                "instruction": {"type": "string", "description": "User summary instruction.", "default": ""},
                "summary_quality": {"type": "string", "enum": ["fast", "pro"], "description": "Summary model tier.", "default": "fast"},
                "force_refresh": {"type": "boolean", "description": "Ignore cached results.", "default": False},
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "easysourceflow_submit_batch",
        "description": "Submit multiple public URLs for background processing and return a batch ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "urls": {"type": "array", "items": {"type": "string"}, "description": "Public URLs to process."},
                "instruction": {"type": "string", "description": "Shared summary instruction.", "default": ""},
                "summary_quality": {"type": "string", "enum": ["fast", "pro"], "description": "Use fast for the configured normal model, or pro for the configured strong model. Video links are automatically treated as pro.", "default": "fast"},
                "force_refresh": {"type": "boolean", "description": "Ignore cached results for every URL in the batch.", "default": False},
            },
            "required": ["urls"],
        },
    },
    {
        "name": "easysourceflow_get_batch",
        "description": "Get status and per-link jobs for a batch.",
        "inputSchema": {
            "type": "object",
            "properties": {"batch_id": {"type": "string", "description": "Batch ID returned by easysourceflow_submit_batch."}},
            "required": ["batch_id"],
        },
    },
    {
        "name": "easysourceflow_list_recent_jobs",
        "description": "List recent EasySourceFlow jobs from the local SQLite store.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
                "status": {"type": "string", "description": "Optional job status filter."},
            },
        },
    },
    {
        "name": "easysourceflow_health_check",
        "description": "Check EasySourceFlow dependencies and runtime configuration.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "easysourceflow_search_outputs",
        "description": "Full-text search generated Markdown outputs and return links to the stored Markdown files.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "q": {"type": "string", "description": "Search query."},
                "source": {"type": "string", "description": "Optional source type filter."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50},
            },
            "required": ["q"],
        },
    },
    {
        "name": "easysourceflow_bilibili_cookie_status",
        "description": "Check whether the configured Bilibili cookies file exists without exposing its contents.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "easysourceflow_model_status",
        "description": "Show model provider/model configuration without exposing API keys.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "easysourceflow_cleanup",
        "description": "Preview or remove old EasySourceFlow temporary artifacts. Defaults to dry-run.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "minimum": 1, "default": 14},
                "dry_run": {"type": "boolean", "default": True},
            },
        },
    },
    {
        "name": "easysourceflow_backup",
        "description": "Back up the local EasySourceFlow SQLite database and output directory.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


_READ_ONLY_TOOLS = {
    "easysourceflow_get_job",
    "easysourceflow_get_batch",
    "easysourceflow_list_recent_jobs",
    "easysourceflow_health_check",
    "easysourceflow_search_outputs",
    "easysourceflow_bilibili_cookie_status",
    "easysourceflow_model_status",
}
_OPEN_WORLD_TOOLS = {
    "easysourceflow_summarize_link",
    "easysourceflow_submit_link",
    "easysourceflow_retry_job",
    "easysourceflow_submit_document",
    "easysourceflow_submit_document_file",
    "easysourceflow_submit_batch",
}
_DESTRUCTIVE_TOOLS = {"easysourceflow_cancel_job", "easysourceflow_cleanup"}

for _tool in TOOLS:
    _tool["inputSchema"]["additionalProperties"] = False
    _tool["annotations"] = {
        "readOnlyHint": _tool["name"] in _READ_ONLY_TOOLS,
        "destructiveHint": _tool["name"] in _DESTRUCTIVE_TOOLS,
        "idempotentHint": _tool["name"] in _READ_ONLY_TOOLS,
        "openWorldHint": _tool["name"] in _OPEN_WORLD_TOOLS,
    }

_TOOLS_BY_NAME = {tool["name"]: tool for tool in TOOLS}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", stream=sys.stderr)
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            logger.warning("received invalid JSON-RPC input")
            response = _rpc_error(None, -32700, "Parse error: request is not valid JSON.")
        else:
            response = handle_message(message)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


def handle_message(message: Any) -> Dict[str, Any] | None:
    if not isinstance(message, dict):
        return _rpc_error(None, -32600, "Invalid Request: expected a JSON object.")
    method = message.get("method")
    message_id = message.get("id")
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": message_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "easysourceflow_mcp", "version": __version__},
            },
        }
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": message_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = message.get("params")
        if params is None:
            params = {}
        if not isinstance(params, dict):
            return _rpc_error(message_id, -32602, "Invalid params: expected an object.")
        arguments = params.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            result = _tool_error("Invalid arguments: expected an object.")
        else:
            result = call_tool(params.get("name"), arguments)
        return {"jsonrpc": "2.0", "id": message_id, "result": result}
    if message_id is None:
        return None
    return _rpc_error(message_id, -32601, f"Unknown method: {method}")


def call_tool(name: Any, arguments: Dict[str, Any]) -> dict:
    validation_error = _validate_tool_arguments(name, arguments)
    if validation_error:
        return _tool_error(validation_error)
    try:
        if name == "easysourceflow_summarize_link":
            source_type = detect_source_type(arguments.get("url", ""))
            if source_type in {"bilibili", "youtube"}:
                payload = {
                    "error": {
                        "code": "video_requires_async",
                        "message": "Video links must be processed with the durable asynchronous workflow.",
                        "next_steps": [
                            "Call easysourceflow_submit_link with the same URL.",
                            "Retain its job_id and call easysourceflow_get_job with wait_seconds=45 until terminal.",
                            "Do not use another fetch or summarization tool as a fallback.",
                        ],
                    }
                }
            else:
                payload = _post_json(
                    "/summarize",
                    {
                        "url": arguments.get("url", ""),
                        "instruction": arguments.get("instruction", ""),
                        "summary_quality": arguments.get("summary_quality", "fast"),
                        "force_refresh": arguments.get("force_refresh", False),
                    },
                )
        elif name == "easysourceflow_submit_link":
            payload = _post_json(
                "/jobs",
                {
                    "url": arguments.get("url", ""),
                    "instruction": arguments.get("instruction", ""),
                    "summary_quality": arguments.get("summary_quality", "fast"),
                    "force_refresh": arguments.get("force_refresh", False),
                },
            )
        elif name == "easysourceflow_get_job":
            payload = _get_job_with_wait(
                arguments.get("job_id", ""),
                arguments.get("wait_seconds", 0),
            )
        elif name == "easysourceflow_favorite_result":
            payload = _favorite_result(arguments)
        elif name == "easysourceflow_retry_job":
            body = {}
            if "instruction" in arguments:
                body["instruction"] = arguments.get("instruction", "")
            if "summary_quality" in arguments:
                body["summary_quality"] = arguments.get("summary_quality", "fast")
            body["force_refresh"] = arguments.get("force_refresh", True)
            payload = _post_json(f"/jobs/{arguments.get('job_id', '')}/retry", body)
        elif name == "easysourceflow_cancel_job":
            payload = _post_json(f"/jobs/{arguments.get('job_id', '')}/cancel", {})
        elif name == "easysourceflow_submit_document":
            payload = _post_json(
                "/documents",
                {
                    "title": arguments.get("title", "local-document"),
                    "content": arguments.get("content", ""),
                    "source_url": arguments.get("source_url", ""),
                    "instruction": arguments.get("instruction", ""),
                    "summary_quality": arguments.get("summary_quality", "fast"),
                    "force_refresh": arguments.get("force_refresh", False),
                },
            )
        elif name == "easysourceflow_submit_document_file":
            payload = _submit_document_file(arguments)
        elif name == "easysourceflow_submit_batch":
            payload = _post_json(
                "/batches",
                {
                    "urls": arguments.get("urls", []),
                    "instruction": arguments.get("instruction", ""),
                    "summary_quality": arguments.get("summary_quality", "fast"),
                    "force_refresh": arguments.get("force_refresh", False),
                },
            )
        elif name == "easysourceflow_get_batch":
            payload = _get_json(f"/batches/{arguments.get('batch_id', '')}")
        elif name == "easysourceflow_list_recent_jobs":
            query = {k: v for k, v in arguments.items() if v is not None}
            path = "/jobs"
            if query:
                path = f"{path}?{urlencode(query)}"
            payload = _get_json(path)
        elif name == "easysourceflow_health_check":
            payload = _get_json("/health")
        elif name == "easysourceflow_search_outputs":
            query = {
                "q": arguments.get("q", ""),
                "source": arguments.get("source", ""),
                "limit": arguments.get("limit", 50),
            }
            payload = _get_json(f"/search?{urlencode(query)}")
        elif name == "easysourceflow_bilibili_cookie_status":
            payload = _get_json("/cookies/bilibili")
        elif name == "easysourceflow_model_status":
            payload = _get_json("/model")
        elif name == "easysourceflow_cleanup":
            payload = _post_json(
                "/cleanup",
                {"days": arguments.get("days", 14), "dry_run": arguments.get("dry_run", True)},
            )
        elif name == "easysourceflow_backup":
            payload = _post_json("/backup", {})
    except Exception as exc:
        logger.exception("tool call failed tool=%s", name)
        return _tool_error(f"Could not call easysourceflowd at {BASE_URL}: {type(exc).__name__}.")

    text = _format_payload(payload)
    is_error = payload.get("status") == "failed" or "error" in payload
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": payload,
        "isError": is_error,
    }


def _submit_document_file(arguments: Dict[str, Any]) -> dict:
    try:
        path = Path(str(arguments.get("file_path") or "")).expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        return _document_file_error("uploaded_file_missing", "The uploaded attachment is no longer available.")
    if not path.is_file():
        return _document_file_error("uploaded_file_missing", "The uploaded attachment is not a regular file.")
    if not any(_is_relative_to(path, root) for root in _document_import_roots()):
        return _document_file_error(
            "document_path_not_allowed",
            "The attachment is outside the configured Agent upload directories.",
            ["Add the upload directory to EASYSOURCEFLOW_DOCUMENT_IMPORT_ROOTS and restart the Agent gateway."],
        )
    allowed_suffixes = {".txt", ".md", ".markdown", ".html", ".htm", ".docx", ".epub", ".pdf"}
    if path.suffix.lower() not in allowed_suffixes:
        return _document_file_error("unsupported_document", "This attachment type is not supported.")
    max_bytes = _document_import_max_bytes()
    try:
        size = path.stat().st_size
    except OSError:
        return _document_file_error("uploaded_file_missing", "The uploaded attachment could not be inspected.")
    if size <= 0 or size > max_bytes:
        return _document_file_error(
            "document_too_large",
            f"The attachment must be between 1 byte and {max_bytes // (1024 * 1024)} MiB.",
        )
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return _document_file_error("uploaded_file_unreadable", "The uploaded attachment could not be read.")
    return _post_json(
        "/documents",
        {
            "title": str(arguments.get("title") or path.name),
            "data_base64": encoded,
            "mime_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            "instruction": arguments.get("instruction", ""),
            "summary_quality": arguments.get("summary_quality", "fast"),
            "force_refresh": arguments.get("force_refresh", False),
        },
    )


def _document_import_roots() -> list[Path]:
    roots = [Path.home() / ".openclaw" / "media" / "inbound"]
    configured = os.environ.get("EASYSOURCEFLOW_DOCUMENT_IMPORT_ROOTS", "")
    for value in configured.split(os.pathsep):
        if value.strip():
            roots.append(Path(value.strip()).expanduser())
    resolved = []
    for root in roots:
        try:
            resolved.append(root.resolve())
        except OSError:
            continue
    return resolved


def _document_import_max_bytes() -> int:
    try:
        configured = int(os.environ.get("EASYSOURCEFLOW_DOCUMENT_IMPORT_MAX_BYTES", "52428800"))
    except ValueError:
        return 50 * 1024 * 1024
    return max(1, min(configured, 200 * 1024 * 1024))


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _document_file_error(code: str, message: str, next_steps: list[str] | None = None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "next_steps": next_steps or ["Upload the document again and retry."],
        }
    }


def _validate_tool_arguments(name: Any, arguments: Dict[str, Any]) -> str:
    if not isinstance(name, str) or name not in _TOOLS_BY_NAME:
        return f"Unknown tool: {name}"
    schema = _TOOLS_BY_NAME[name]["inputSchema"]
    properties = schema.get("properties", {})
    unknown = sorted(set(arguments) - set(properties))
    if unknown:
        return f"Invalid arguments for {name}: unknown field '{unknown[0]}'."
    for field in schema.get("required", []):
        if field not in arguments:
            return f"Invalid arguments for {name}: '{field}' is required."
    for field, value in arguments.items():
        field_schema = properties[field]
        expected = field_schema.get("type")
        if not _matches_json_type(value, expected):
            return f"Invalid arguments for {name}: '{field}' must be {expected}."
        if field in schema.get("required", []) and expected == "string" and not value.strip():
            return f"Invalid arguments for {name}: '{field}' must not be empty."
        if field in schema.get("required", []) and expected == "array" and not value:
            return f"Invalid arguments for {name}: '{field}' must not be empty."
        if "enum" in field_schema and value not in field_schema["enum"]:
            choices = ", ".join(str(item) for item in field_schema["enum"])
            return f"Invalid arguments for {name}: '{field}' must be one of {choices}."
        if expected == "integer":
            if "minimum" in field_schema and value < field_schema["minimum"]:
                return f"Invalid arguments for {name}: '{field}' is below the minimum."
            if "maximum" in field_schema and value > field_schema["maximum"]:
                return f"Invalid arguments for {name}: '{field}' is above the maximum."
        if expected == "array":
            item_type = (field_schema.get("items") or {}).get("type")
            if item_type and any(not _matches_json_type(item, item_type) for item in value):
                return f"Invalid arguments for {name}: every '{field}' item must be {item_type}."
    return ""


def _matches_json_type(value: Any, expected: str | None) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return True


def _post_json(path: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        f"{BASE_URL}{path}",
        data=body,
        headers={"content-type": "application/json", **_CLIENT_HEADERS},
        method="POST",
    )
    return _read_json(request)


def _get_json(path: str) -> dict:
    return _read_json(Request(f"{BASE_URL}{path}", headers=_CLIENT_HEADERS, method="GET"))


def _get_job_with_wait(job_id: str, wait_seconds: int) -> dict:
    deadline = time.monotonic() + wait_seconds
    payload = _get_json(f"/jobs/{job_id}")
    while payload.get("status") in {"queued", "running"} and time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(2.0, remaining))
        payload = _get_json(f"/jobs/{job_id}")

    if payload.get("status") in {"queued", "running"}:
        payload = dict(payload)
        payload["polling"] = {
            "complete": False,
            "next_action": "Call easysourceflow_get_job again with the same job_id and wait_seconds=45.",
            "fallback_allowed": False,
        }
    return payload


def _favorite_result(arguments: Dict[str, Any]) -> dict:
    relative_path = str(arguments.get("relative_path") or "").strip()
    if not relative_path:
        output_path = str(arguments.get("output_markdown_path") or "").strip()
        job_id = str(arguments.get("job_id") or "").strip()
        if job_id:
            job = _get_json(f"/jobs/{job_id}")
            result = job.get("result") or {}
            output_path = str(result.get("output_markdown_path") or output_path)
        relative_path = _relative_output_path(output_path)
    if not relative_path:
        outputs = _get_json("/outputs")
        items = outputs.get("items") or []
        if not items:
            return {"error": {"code": "not_found", "message": "No EasySourceFlow output is available to favorite."}}
        relative_path = str(items[0].get("relative_path") or "")
    payload = _post_json("/favorites", {"relative_path": relative_path})
    if payload.get("ok"):
        payload["message"] = "已收藏这篇总结。"
    return payload


def _relative_output_path(output_markdown_path: str) -> str:
    if not output_markdown_path:
        return ""
    outputs = _get_json("/outputs")
    for item in outputs.get("items") or []:
        if str(item.get("output_markdown_path") or "") == output_markdown_path:
            return str(item.get("relative_path") or "")
    return ""


def _read_json(request: Request) -> dict:
    try:
        with urlopen(request, timeout=60) as response:
            return _decode_json_response(response.read(), response.status)
    except HTTPError as exc:
        raw = exc.read()
        try:
            payload = _decode_json_response(raw, exc.code)
            if "error" not in payload:
                payload["error"] = {"code": "http_error", "message": f"HTTP {exc.code}"}
            return payload
        except json.JSONDecodeError:
            message = raw.decode("utf-8", errors="replace").strip() or str(exc.reason)
            return {"error": {"code": "http_error", "message": f"HTTP {exc.code}: {message[:500]}"}}
    except (URLError, TimeoutError, OSError) as exc:
        return {"error": {"code": "connection_error", "message": f"Could not reach EasySourceFlow daemon: {type(exc).__name__}."}}


def _decode_json_response(raw: bytes, status: int) -> dict:
    text = raw.decode("utf-8", errors="replace")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        if status >= 400:
            raise
        return {"error": {"code": "invalid_json", "message": f"EasySourceFlow returned non-JSON response: {text[:500]}"}}
    if isinstance(payload, dict):
        return payload
    return {"error": {"code": "invalid_json", "message": "EasySourceFlow returned a JSON value that is not an object."}}


def _format_payload(payload: dict) -> str:
    result = payload.get("result") or {}
    if result.get("summary_markdown"):
        output_path = result.get("output_markdown_path") or ""
        summary = str(result["summary_markdown"]).rstrip()
        return (
            "<!-- EasySourceFlow final Markdown. Relay the Markdown below verbatim unless the user explicitly "
            "asks for rewriting. For chat-card delivery, send it via message tool `card`, with this Markdown as "
            "`card.elements[0].content`; never put card JSON in `message`. If the user replies exactly '收藏', "
            f"call easysourceflow_favorite_result with this output path. output_markdown_path={output_path} -->\n"
            f"{summary}"
        )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _tool_error(message: str) -> dict:
    return {"content": [{"type": "text", "text": message}], "isError": True}


def _rpc_error(message_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}


if __name__ == "__main__":
    main()
