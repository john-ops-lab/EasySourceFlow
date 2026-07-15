"""URL validation, normalization, and source detection."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from .errors import invalid_url

TRACKING_PREFIXES = ("utm_",)
TRACKING_PARAMS = {"fbclid", "gclid", "igshid", "spm", "vd_source"}


def normalize_url(url: str, allow_local_urls: bool = False) -> str:
    raw = (url or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        raise invalid_url("Only http and https URLs are supported.")
    if not parsed.netloc:
        raise invalid_url("URL must include a host.")
    _validate_public_host(parsed.hostname or "", allow_local_urls)

    filtered_query = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key in TRACKING_PARAMS or any(key.startswith(prefix) for prefix in TRACKING_PREFIXES):
            continue
        filtered_query.append((key, value))

    cleaned = parsed._replace(
        fragment="",
        query=urlencode(filtered_query, doseq=True),
        netloc=parsed.netloc.lower(),
    )
    return urlunparse(cleaned)


def detect_source_type(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if host.endswith("mp.weixin.qq.com"):
        return "wechat"
    if host.endswith("youtube.com") or host.endswith("youtu.be"):
        return "youtube"
    if host.endswith("bilibili.com") or host.endswith("b23.tv"):
        return "bilibili"
    return "web"


def _validate_public_host(host: str, allow_local_urls: bool) -> None:
    if allow_local_urls:
        return
    lowered = host.lower()
    if lowered in {"localhost"} or lowered.endswith(".localhost"):
        raise invalid_url("Localhost URLs are disabled by default.")

    try:
        addresses = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise invalid_url(f"Could not resolve URL host: {host}") from exc

    for item in addresses:
        ip = ipaddress.ip_address(item[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
        ):
            raise invalid_url("Private, local, and reserved network URLs are disabled by default.")
