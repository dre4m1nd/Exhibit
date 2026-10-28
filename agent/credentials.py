# -*- coding: utf-8 -*-
"""Local credential storage for model providers."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .providers import get_provider, validate_base_url

CONFIG_ENV = "EXHIBIT_CONFIG_DIR"


@dataclass(frozen=True)
class SavedCredential:
    """A provider credential with its selected model."""

    provider: str
    base_url: str
    model: str
    api_key: str

    def masked(self) -> str:
        """Return a safe summary for protocol messages and logs."""
        return f"{self.provider} · {self.model} · {_mask(self.api_key)}"


def config_dir() -> Path:
    """Return the user-level credential directory."""
    override = os.getenv(CONFIG_ENV)
    if override:
        return Path(override).expanduser().resolve()
    root = os.getenv("APPDATA") or Path.home()
    return Path(root) / "Exhibit"


def credentials_path() -> Path:
    return config_dir() / "credentials.json"


def load_credentials() -> dict[str, SavedCredential]:
    """Read saved credentials, returning an empty map if none exist."""
    path = credentials_path()
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get("providers", data)
    if not isinstance(raw, dict):
        raise ValueError("credentials file must contain a providers object")
    saved: dict[str, SavedCredential] = {}
    for key, value in raw.items():
        if not isinstance(value, dict):
            continue
        saved[key] = SavedCredential(
            provider=key,
            base_url=str(value.get("base_url", "")),
            model=str(value.get("model", "")),
            api_key=str(value.get("api_key", "")),
        )
    return saved


def save_credential(
    provider: str,
    api_key: str,
    model: str = "",
    base_url: str = "",
) -> SavedCredential:
    """Validate and persist one provider credential."""
    key = api_key.strip()
    if not key:
        raise ValueError("API key is required")
    known = get_provider(provider)
    endpoint_input = base_url.strip() or known.base_url
    if not endpoint_input:
        raise ValueError("base URL is required for a custom endpoint")
    endpoint = validate_base_url(endpoint_input, provider=known.key)
    selected_model = model.strip() or (known.models[0] if known.models else "")
    if not selected_model:
        raise ValueError("model is required for a custom endpoint")
    credential = SavedCredential(
        provider=known.key,
        base_url=endpoint,
        model=selected_model,
        api_key=key,
    )

    current = load_credentials()
    current[known.key] = credential
    path = credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "providers": {
            name: {
                "base_url": item.base_url,
                "model": item.model,
                "api_key": item.api_key,
            }
            for name, item in current.items()
        },
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if os.name != "nt":
        temporary.chmod(0o600)
    temporary.replace(path)
    return credential


def remove_credential(provider: str) -> bool:
    """Delete one saved provider credential."""
    current = load_credentials()
    if provider not in current:
        return False
    del current[provider]
    path = credentials_path()
    payload = {
        "version": 1,
        "providers": {
            name: {
                "base_url": item.base_url,
                "model": item.model,
                "api_key": item.api_key,
            }
            for name, item in current.items()
        },
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return True


def _mask(api_key: str) -> str:
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return f"{api_key[:4]}…{api_key[-4:]}"


__all__ = [
    "CONFIG_ENV",
    "SavedCredential",
    "config_dir",
    "credentials_path",
    "load_credentials",
    "remove_credential",
    "save_credential",
]
