import socket
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.request import Request

from easysourceflow_core.errors import EasySourceFlowError, invalid_url
from easysourceflow_core.extractors.web import extract_web_document
from easysourceflow_core.url_utils import (
    _ValidatingRedirectHandler,
    normalize_fake_ip_cidrs,
    normalize_url,
)


def _records(address: str) -> list[tuple]:
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, 0))]


class UrlValidationTests(unittest.TestCase):
    def test_strict_mode_rejects_fake_ip_resolution(self):
        with patch("easysourceflow_core.url_utils.socket.getaddrinfo", return_value=_records("198.18.0.30")):
            with self.assertRaises(EasySourceFlowError) as error:
                normalize_url("https://www.bilibili.com/video/BV1example")
        self.assertEqual(error.exception.code, "invalid_url")
        self.assertIn("Fake-IP range 198.18.0.0/15", error.exception.message)
        self.assertTrue(any("网络与安全" in step for step in error.exception.next_steps))

    def test_trusted_mode_allows_configured_fake_ip_for_domain(self):
        with patch("easysourceflow_core.url_utils.socket.getaddrinfo", return_value=_records("198.18.0.30")):
            normalized = normalize_url(
                "https://www.bilibili.com/video/BV1example",
                trusted_fake_ip_cidrs="198.18.0.0/15",
            )
        self.assertEqual(normalized, "https://www.bilibili.com/video/BV1example")

    def test_trusted_mode_does_not_allow_direct_fake_ip_url(self):
        with self.assertRaises(EasySourceFlowError) as error:
            normalize_url("http://198.18.0.30/", trusted_fake_ip_cidrs="198.18.0.0/15")
        self.assertEqual(error.exception.code, "invalid_url")

    def test_custom_documentation_range_requires_explicit_trust(self):
        records = _records("198.51.100.20")
        with patch("easysourceflow_core.url_utils.socket.getaddrinfo", return_value=records):
            with self.assertRaises(EasySourceFlowError):
                normalize_url("https://proxy.example/path")
        with patch("easysourceflow_core.url_utils.socket.getaddrinfo", return_value=records):
            normalized = normalize_url(
                "https://proxy.example/path",
                trusted_fake_ip_cidrs="198.51.100.0/24",
            )
        self.assertEqual(normalized, "https://proxy.example/path")

    def test_real_private_and_loopback_addresses_remain_blocked(self):
        for address in ("10.0.0.5", "127.0.0.1", "169.254.0.1"):
            with self.subTest(address=address):
                with patch("easysourceflow_core.url_utils.socket.getaddrinfo", return_value=_records(address)):
                    with self.assertRaises(EasySourceFlowError):
                        normalize_url("http://internal.example/path")

    def test_rejects_global_or_protected_trusted_cidrs(self):
        for cidr in (
            "8.8.8.0/24",
            "127.0.0.0/8",
            "169.254.0.0/16",
            "240.0.0.0/4",
            "::ffff:0:0/96",
            "ff00::/8",
        ):
            with self.subTest(cidr=cidr):
                with self.assertRaises(ValueError):
                    normalize_fake_ip_cidrs(cidr)

    def test_redirect_target_is_revalidated(self):
        handler = _ValidatingRedirectHandler(False, "198.18.0.0/15")
        request = Request("https://public.example/start")
        with patch("easysourceflow_core.url_utils.socket.getaddrinfo", return_value=_records("10.0.0.5")):
            with self.assertRaises(EasySourceFlowError):
                handler.redirect_request(request, None, 302, "Found", {}, "http://internal.example/secret")

    def test_security_rejection_does_not_fall_back_to_jina(self):
        settings = SimpleNamespace(
            allow_local_urls=False,
            trusted_fake_ip_cidrs="",
            request_timeout_seconds=5,
            max_content_chars=10000,
        )
        with (
            patch("easysourceflow_core.extractors.web.normalize_url", return_value="https://public.example/start"),
            patch(
                "easysourceflow_core.extractors.web._fetch_html",
                side_effect=invalid_url("Redirect target is private."),
            ),
            patch("easysourceflow_core.extractors.web._fetch_jina_reader_safe") as fallback,
        ):
            with self.assertRaises(EasySourceFlowError) as error:
                extract_web_document("https://public.example/start", settings)
        self.assertEqual(error.exception.code, "invalid_url")
        fallback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
