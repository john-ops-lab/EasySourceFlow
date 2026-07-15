"""Optional, minimal notifications for jobs and maintenance."""

from __future__ import annotations

import json
import logging
import shlex
import subprocess
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .config import Settings


logger = logging.getLogger(__name__)


def notify_event(settings: Settings, event: str, details: dict[str, Any]) -> dict:
    enabled = {item.strip() for item in settings.notification_events.split(",") if item.strip()}
    if event not in enabled:
        return {"sent": False, "event": event, "reason": "disabled", "channels": []}
    payload = _safe_payload(event, details)
    channels = []
    if settings.notification_webhook_url.strip():
        channels.append(_send_webhook(settings, payload))
    if settings.notification_command.strip():
        channels.append(_run_command(settings.notification_command, payload))
    return {
        "sent": bool(channels) and any(channel.get("ok") for channel in channels),
        "event": event,
        "channels": channels,
        "reason": "no_channels" if not channels else "",
    }


def _safe_payload(event: str, details: dict[str, Any]) -> dict:
    allowed = {
        "job_id",
        "status",
        "title",
        "error_code",
        "error_message",
        "output_markdown_path",
        "resource_package_path",
        "maintenance_status",
    }
    payload = {key: details.get(key) for key in allowed if details.get(key) not in {None, ""}}
    if "error_message" in payload:
        payload["error_message"] = str(payload["error_message"])[:500]
    payload["event"] = event
    payload["occurred_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return payload


def _send_webhook(settings: Settings, payload: dict) -> dict:
    url = settings.notification_webhook_url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        logger.error("notification webhook URL is invalid")
        return {"channel": "webhook", "ok": False, "error": "invalid_url"}
    headers = {"content-type": "application/json"}
    if settings.notification_webhook_token:
        headers["authorization"] = f"Bearer {settings.notification_webhook_token}"
    request = Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers=headers, method="POST")
    try:
        with urlopen(request, timeout=10) as response:
            ok = 200 <= response.status < 300
        return {"channel": "webhook", "ok": ok, "status": response.status}
    except Exception as exc:
        logger.warning("notification webhook failed error=%s", type(exc).__name__)
        return {"channel": "webhook", "ok": False, "error": type(exc).__name__}


def _run_command(command: str, payload: dict) -> dict:
    try:
        args = shlex.split(command)
    except ValueError:
        return {"channel": "command", "ok": False, "error": "invalid_command"}
    if not args:
        return {"channel": "command", "ok": False, "error": "invalid_command"}
    try:
        completed = subprocess.run(
            args,
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
        return {"channel": "command", "ok": completed.returncode == 0, "returncode": completed.returncode}
    except Exception as exc:
        logger.warning("notification command failed error=%s", type(exc).__name__)
        return {"channel": "command", "ok": False, "error": type(exc).__name__}
