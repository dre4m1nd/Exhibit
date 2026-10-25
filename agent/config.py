# -*- coding: utf-8 -*-
"""Runtime configuration for Exhibit, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from ipaddress import ip_address
from urllib.parse import urlparse

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-5.4-mini"


@dataclass(frozen=True)
class Config:
    """The agent configuration resolved from the environment."""

    base_url: str
    api_key: str
    model: str
    max_iters: int
    request_timeout: float


def load_config() -> Config:
    """Build the config and reject local gateways or missing credentials."""
    api_key = os.getenv("EXHIBIT_API_KEY", "").strip()
    if not api_key:
        raise ValueError("EXHIBIT_API_KEY is required")

    base_url = os.getenv("EXHIBIT_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    _validate_remote_url(base_url)
    return Config(
        base_url=base_url,
        api_key=api_key,
        model=os.getenv("EXHIBIT_MODEL", DEFAULT_MODEL),
        max_iters=int(os.getenv("EXHIBIT_MAX_ITERS", "60")),
        request_timeout=float(os.getenv("EXHIBIT_TIMEOUT", "600")),
    )


def _validate_remote_url(base_url: str) -> None:
    """Reject local, private, and non-HTTPS model endpoints."""
    parsed = urlparse(base_url)
    if parsed.scheme != "https":
        raise ValueError("EXHIBIT_BASE_URL must use https")
    host = parsed.hostname
    if not host:
        raise ValueError("EXHIBIT_BASE_URL must include a host")
    normalized_host = host.rstrip(".").lower()
    if normalized_host == "localhost" or normalized_host.endswith(
        (".localhost", ".localdomain")
    ):
        raise ValueError("EXHIBIT_BASE_URL must not point to localhost")
    try:
        address = ip_address(normalized_host)
    except ValueError:
        return
    if not address.is_global:
        raise ValueError(
            "EXHIBIT_BASE_URL must not point to a local or private address"
        )
