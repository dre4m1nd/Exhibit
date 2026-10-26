# -*- coding: utf-8 -*-
"""Runtime configuration for Exhibit, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from ipaddress import ip_address
from urllib.parse import urlparse

from .credentials import SavedCredential, load_credentials

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
    max_output_tokens: int = 16000


def load_config() -> Config:
    """Build the config from the environment or the TUI's saved login."""
    api_key = os.getenv("EXHIBIT_API_KEY", "").strip()
    saved = None if api_key else _saved_credential()
    if not api_key and saved is None:
        raise ValueError(
            "EXHIBIT_API_KEY is required: no saved credential found "
            "(use /login in the TUI or set EXHIBIT_API_KEY)"
        )

    base_url = os.getenv("EXHIBIT_BASE_URL", "").rstrip("/")
    if not base_url:
        base_url = saved.base_url if saved is not None else DEFAULT_BASE_URL
    _validate_remote_url(base_url)
    return Config(
        base_url=base_url,
        api_key=api_key or (saved.api_key if saved is not None else ""),
        model=os.getenv("EXHIBIT_MODEL")
        or (saved.model if saved is not None else DEFAULT_MODEL),
        max_iters=int(os.getenv("EXHIBIT_MAX_ITERS", "60")),
        request_timeout=float(os.getenv("EXHIBIT_TIMEOUT", "600")),
        max_output_tokens=int(os.getenv("EXHIBIT_MAX_OUTPUT_TOKENS", "16000")),
    )


def _saved_credential() -> SavedCredential | None:
    """Select one saved provider for headless runs without an env key."""
    saved = load_credentials()
    if not saved:
        return None
    requested = os.getenv("EXHIBIT_PROVIDER", "").strip().lower()
    if requested:
        if requested == "custom" and "custom" not in saved:
            # A custom endpoint may be saved under its built-in provider key.
            candidates = [
                item
                for key, item in saved.items()
                if key != "custom" and item.base_url
            ]
            if len(candidates) == 1:
                return candidates[0]
        credential = saved.get(requested)
        if credential is None:
            choices = ", ".join(sorted(saved))
            raise ValueError(
                f"saved provider '{requested}' was not found; available: {choices}"
            )
        return credential
    if len(saved) == 1:
        return next(iter(saved.values()))
    choices = ", ".join(sorted(saved))
    raise ValueError(
        "multiple saved providers are available "
        f"({choices}); set EXHIBIT_PROVIDER or EXHIBIT_API_KEY"
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
