# -*- coding: utf-8 -*-
"""Supported model providers and their OpenAI-compatible endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address
from urllib.parse import urlparse


@dataclass(frozen=True)
class Provider:
    """A remote model provider exposed by ``/login``."""

    key: str
    label: str
    base_url: str
    models: tuple[str, ...]


PROVIDERS: dict[str, Provider] = {
    "openai": Provider(
        key="openai",
        label="OpenAI",
        base_url="https://api.openai.com/v1",
        models=("gpt-5.4-mini",),
    ),
    "deepseek": Provider(
        key="deepseek",
        label="DeepSeek",
        base_url="https://api.deepseek.com/v1",
        models=("deepseek-chat", "deepseek-reasoner"),
    ),
    "qwen": Provider(
        key="qwen",
        label="Qwen",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        models=("qwen-plus", "qwen-coder-plus"),
    ),
    "openrouter": Provider(
        key="openrouter",
        label="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        models=("openrouter/free",),
    ),
    "custom": Provider(
        key="custom",
        label="自定义 OpenAI 兼容端点",
        base_url="",
        models=(),
    ),
}


def get_provider(key: str) -> Provider:
    """Return a provider by key or explain the available choices."""
    try:
        return PROVIDERS[key]
    except KeyError as exc:
        choices = ", ".join(PROVIDERS)
        raise KeyError(f"unknown provider '{key}', expected one of {choices}") from exc


LOOPBACK_HOSTS = {"127.0.0.1", "::1"}


def validate_base_url(base_url: str, *, provider: str | None = None) -> str:
    """Normalize an endpoint, allowing loopback only for custom providers."""
    normalized = base_url.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.username or parsed.password:
        raise ValueError("model endpoint must not contain credentials")
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("model endpoint must use http or https")
    if not parsed.hostname:
        raise ValueError("model endpoint must include a host")
    host = parsed.hostname.rstrip(".").lower()
    if provider == "custom" and host in LOOPBACK_HOSTS:
        return normalized
    if parsed.scheme != "https":
        raise ValueError("model endpoint must use https")
    if host == "localhost" or host.endswith((".localhost", ".localdomain")):
        raise ValueError("model endpoint must not point to localhost")
    try:
        address = ip_address(host)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise ValueError("model endpoint must not point to a private address")
    return normalized


__all__ = [
    "LOOPBACK_HOSTS",
    "PROVIDERS",
    "Provider",
    "get_provider",
    "validate_base_url",
]
