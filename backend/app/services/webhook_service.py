"""Fire webhook callbacks asynchronously when a bin is generated."""

from __future__ import annotations

import ipaddress
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

WEBHOOK_TIMEOUT = 30  # seconds
_WEBHOOK_WORKERS = 4

_executor = ThreadPoolExecutor(max_workers=_WEBHOOK_WORKERS)

_BLOCKED_HOSTS: set[str] = {"localhost", "0.0.0.0", "127.0.0.1", "::1"}
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("fc00::/7"),
]


def _is_safe_url(url: str) -> bool:
    """Return True if *url* uses http/https and does not target an internal
    or private address.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.scheme not in ("http", "https"):
        return False

    host = (parsed.hostname or "").lower()
    if not host:
        return False

    if host in _BLOCKED_HOSTS:
        return False

    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        # Not a raw IP — allow DNS resolution to happen at POST time.
        return True

    if addr.is_loopback or addr.is_link_local or addr.is_private or addr.is_unspecified:
        return False

    for net in _BLOCKED_NETWORKS:
        if addr in net:
            return False

    return True


def fire_webhook(
    webhook_url: str,
    payload: dict[str, Any],
) -> None:
    """POST *payload* to *webhook_url* in a background thread.

    The URL is validated before dispatch — internal/private addresses are
    refused.  Network errors and non-2xx responses are logged but never
    raised to the caller (the generate response is not delayed or blocked).

    A bounded thread pool limits concurrency so a flood of webhooks cannot
    exhaust process resources; excess submissions block until a worker is
    free.
    """

    def _post() -> None:
        try:
            with httpx.Client(timeout=WEBHOOK_TIMEOUT) as client:
                resp = client.post(
                    webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                if resp.is_success:
                    logger.info(
                        "webhook delivered to %s (status %s)",
                        webhook_url,
                        resp.status_code,
                    )
                else:
                    logger.warning(
                        "webhook to %s returned %s: %s",
                        webhook_url,
                        resp.status_code,
                        resp.text[:500],
                    )
        except Exception:
            logger.exception("webhook to %s failed", webhook_url)

    if not _is_safe_url(webhook_url):
        logger.warning("webhook refused (unsafe URL): %s", webhook_url)
        return

    _executor.submit(_post)
