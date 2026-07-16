"""URL validation, normalization, and source detection."""

from __future__ import annotations

import ipaddress
import re
import socket
from collections.abc import Iterable
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .errors import invalid_url

TRACKING_PREFIXES = ("utm_",)
TRACKING_PARAMS = {"fbclid", "gclid", "igshid", "spm", "vd_source"}
DEFAULT_FAKE_IP_CIDRS = ("198.18.0.0/15",)
_NEVER_TRUSTED_CIDRS = tuple(
    ipaddress.ip_network(value)
    for value in (
        "0.0.0.0/8",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "224.0.0.0/4",
        "240.0.0.0/4",
        "::/128",
        "::1/128",
        "::ffff:0:0/96",
        "fe80::/10",
        "ff00::/8",
    )
)


def normalize_url(
    url: str,
    allow_local_urls: bool = False,
    trusted_fake_ip_cidrs: str | Iterable[str] = (),
) -> str:
    raw = (url or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        raise invalid_url("Only http and https URLs are supported.")
    if not parsed.netloc:
        raise invalid_url("URL must include a host.")
    _validate_public_host(parsed.hostname or "", allow_local_urls, trusted_fake_ip_cidrs)

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


def normalize_fake_ip_cidrs(value: str | Iterable[str]) -> tuple[str, ...]:
    raw_values = re.split(r"[\s,]+", value.strip()) if isinstance(value, str) else list(value)
    normalized: list[str] = []
    for raw in raw_values:
        candidate = str(raw).strip()
        if not candidate:
            continue
        try:
            network = ipaddress.ip_network(candidate, strict=False)
        except ValueError as exc:
            raise ValueError(f"Invalid fake-ip CIDR: {candidate}") from exc
        if network.is_global:
            raise ValueError(f"Fake-ip CIDR must not be globally routable: {network}")
        if any(network.version == blocked.version and network.overlaps(blocked) for blocked in _NEVER_TRUSTED_CIDRS):
            raise ValueError(f"Fake-ip CIDR overlaps a protected local range: {network}")
        text = str(network)
        if text not in normalized:
            normalized.append(text)
    if len(normalized) > 32:
        raise ValueError("At most 32 fake-ip CIDRs are supported.")
    return tuple(normalized)


class _ValidatingRedirectHandler(HTTPRedirectHandler):
    def __init__(self, allow_local_urls: bool, trusted_fake_ip_cidrs: str | Iterable[str]) -> None:
        super().__init__()
        self.allow_local_urls = allow_local_urls
        self.trusted_fake_ip_cidrs = trusted_fake_ip_cidrs

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        normalize_url(newurl, self.allow_local_urls, self.trusted_fake_ip_cidrs)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_public_url(
    request: Request,
    timeout: float,
    allow_local_urls: bool = False,
    trusted_fake_ip_cidrs: str | Iterable[str] = (),
):
    opener = build_opener(_ValidatingRedirectHandler(allow_local_urls, trusted_fake_ip_cidrs))
    return opener.open(request, timeout=timeout)


def _validate_public_host(
    host: str,
    allow_local_urls: bool,
    trusted_fake_ip_cidrs: str | Iterable[str] = (),
) -> None:
    if allow_local_urls:
        return
    lowered = host.lower()
    if lowered in {"localhost"} or lowered.endswith(".localhost"):
        raise invalid_url("Localhost URLs are disabled by default.")

    try:
        literal_ip = ipaddress.ip_address(host)
    except ValueError:
        literal_ip = None
    if literal_ip is not None:
        if not literal_ip.is_global:
            raise invalid_url("Private, local, and reserved network URLs are disabled by default.")
        return

    try:
        addresses = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise invalid_url(f"Could not resolve URL host: {host}") from exc

    trusted_networks = tuple(ipaddress.ip_network(value) for value in normalize_fake_ip_cidrs(trusted_fake_ip_cidrs))
    for item in addresses:
        ip = ipaddress.ip_address(item[4][0])
        if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
            raise invalid_url("Private, local, and reserved network URLs are disabled by default.")
        if any(ip.version == network.version and ip in network for network in trusted_networks):
            continue
        if not ip.is_global:
            raise invalid_url("Private, local, and reserved network URLs are disabled by default.")
