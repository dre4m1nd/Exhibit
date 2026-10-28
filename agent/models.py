# -*- coding: utf-8 -*-
"""Discover model IDs for providers that have saved credentials."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .credentials import SavedCredential, load_credentials
from .providers import PROVIDERS, get_provider

DISCOVERY_TIMEOUT = 6.0


def _unique_sorted(models: list[str]) -> list[str]:
    """Remove blank or duplicate IDs and return a deterministic order."""
    unique: dict[str, str] = {}
    for raw in models:
        model = raw.strip()
        unique.setdefault(model.lower(), model)
    return sorted(unique.values(), key=str.lower)


def _fallback_models(
    credential: SavedCredential,
    builtins: tuple[str, ...],
) -> list[str]:
    """Keep known defaults and the provider's explicitly selected model."""
    return _unique_sorted([*builtins, credential.model])


def _failure_message(error: Exception) -> str:
    """Return a short, non-sensitive explanation of a failed discovery."""
    if isinstance(error, HTTPError):
        if error.code in {401, 403}:
            return "API Key 无权限读取模型列表"
        return f"模型列表请求失败（HTTP {error.code}）"
    if isinstance(error, TimeoutError):
        return "模型列表请求超时"
    if isinstance(error, URLError):
        if isinstance(error.reason, TimeoutError):
            return "模型列表请求超时"
        return "无法连接模型端点"
    if isinstance(error, (json.JSONDecodeError, ValueError, TypeError, KeyError)):
        return "模型列表响应格式无效"
    return "模型列表请求失败"


def _fetch_model_ids(
    base_url: str,
    api_key: str,
    timeout: float = DISCOVERY_TIMEOUT,
) -> list[str]:
    """Read model IDs from an OpenAI-compatible ``GET /models`` endpoint."""
    request = Request(
        f"{base_url.rstrip('/')}/models",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
        method="GET",
    )
    with urlopen(request, timeout=timeout) as response:
        payload: Any = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("model response must be an object")
    data = payload.get("data")
    if not isinstance(data, list):
        raise ValueError("model response must contain a data array")
    models = [
        item.get("id")
        for item in data
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    ]
    unique = _unique_sorted(models)
    if not unique:
        raise ValueError("model response contains no model IDs")
    return unique


def discover_models(
    credential: SavedCredential,
    timeout: float = DISCOVERY_TIMEOUT,
) -> tuple[list[str], str]:
    """Return live models plus the saved model, or a safe fallback list."""
    try:
        builtins = get_provider(credential.provider).models
    except KeyError:
        builtins = ()
    try:
        live = _fetch_model_ids(credential.base_url, credential.api_key, timeout)
    except Exception as error:  # noqa: BLE001 - provider responses vary widely
        return _fallback_models(credential, builtins), _failure_message(error)
    return _unique_sorted([*live, credential.model]), ""


def discover_model_catalog(
    current_provider: str | None = None,
    current_model: str | None = None,
) -> dict[str, object]:
    """Return a grouped model catalog for every logged-in provider."""
    saved = load_credentials()
    known_order = [key for key in PROVIDERS if key in saved]
    unknown = sorted(key for key in saved if key not in PROVIDERS)
    keys = [*known_order, *unknown]
    results: dict[str, tuple[list[str], str]] = {}
    if keys:
        with ThreadPoolExecutor(max_workers=min(8, len(keys))) as executor:
            futures = {
                key: executor.submit(discover_models, saved[key])
                for key in keys
            }
            results = {key: future.result() for key, future in futures.items()}

    providers: list[dict[str, object]] = []
    for key in keys:
        credential = saved[key]
        try:
            label = get_provider(key).label
        except KeyError:
            label = key
        models, error = results[key]
        providers.append(
            {
                "key": key,
                "label": label,
                "source": "fallback" if error else "live",
                "error": error,
                "models": models,
            }
        )
    return {
        "kind": "model_catalog",
        "current": {
            "provider": current_provider,
            "model": current_model,
        },
        "providers": providers,
    }


__all__ = [
    "DISCOVERY_TIMEOUT",
    "discover_model_catalog",
    "discover_models",
]
