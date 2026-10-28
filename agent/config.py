# -*- coding: utf-8 -*-
"""Runtime configuration for Exhibit, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from ipaddress import ip_address
from urllib.parse import urlparse

from .credentials import SavedCredential, load_credentials
from .providers import validate_base_url

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-5.4-mini"
OPENROUTER_API_KEY = "OPENROUTER_API_KEY"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "openrouter/free"


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
    exhibit_key = os.getenv("EXHIBIT_API_KEY", "").strip()
    openrouter_key = os.getenv(OPENROUTER_API_KEY, "").strip()
    api_key = exhibit_key or openrouter_key
    saved = None if api_key else _saved_credential()
    if not api_key and saved is None:
        raise ValueError(
            "EXHIBIT_API_KEY or OPENROUTER_API_KEY is required: "
            "no saved credential found (use /login in the TUI or set one)"
        )

    base_url = os.getenv("EXHIBIT_BASE_URL", "").rstrip("/")
    if not base_url:
        if openrouter_key and not exhibit_key:
            base_url = OPENROUTER_BASE_URL
        else:
            base_url = saved.base_url if saved is not None else DEFAULT_BASE_URL
    selected_provider = (
        saved.provider
        if saved is not None
        else os.getenv("EXHIBIT_PROVIDER", "").strip().lower() or None
    )
    _validate_remote_url(base_url, provider=selected_provider)
    return Config(
        base_url=base_url,
        api_key=api_key or (saved.api_key if saved is not None else ""),
        model=os.getenv("EXHIBIT_MODEL")
        or (
            OPENROUTER_MODEL
            if openrouter_key and not exhibit_key
            else saved.model if saved is not None else DEFAULT_MODEL
        ),
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


def _validate_remote_url(base_url: str, *, provider: str | None = None) -> None:
    """Validate an endpoint while keeping loopback limited to custom providers."""
    try:
        validate_base_url(base_url, provider=provider)
    except ValueError as exc:
        raise ValueError(f"EXHIBIT_BASE_URL: {exc}") from exc
