"""LiteRT-LM / llama.cpp provider-profile registration for on-device models."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from providers import register_provider
from providers.base import ProviderProfile

logger = logging.getLogger(__name__)

# model_id → catalog entry for every android_local profile this process
# registered. Lets manage/models report on-device backends without poking
# the global registry shape.
_REGISTERED_CATALOG: dict[str, dict[str, Any]] = {}


def register_android_local_providers(catalog: dict[str, Any] | None = None) -> None:
    """Register on-device provider profiles from the verified catalog.

    Called at boot by RuntimeService. Kotlin managers own download/verify/
    load/loopback-port; the profile only points the agent loop at the local
    OpenAI-compatible server. Model switch -> manage API -> cache-aware
    apply. Chat never bypasses the agent loop.
    """
    if not catalog:
        return

    for model_id, model_info in catalog.items():
        if not isinstance(model_info, dict) or not model_info.get("verified", False):
            continue
        backend = str(model_info.get("backend", "litertlm"))
        port = model_info.get("loopback_port")
        if not port:
            continue

        display = str(model_info.get("display_name", model_id))
        profile = ProviderProfile(
            name=f"android_local_{model_id}",
            display_name=f"On-device: {display}",
            description=f"Local {backend} server on 127.0.0.1:{port}",
            base_url=f"http://127.0.0.1:{port}/v1",
            api_mode="chat_completions",
            auth_type="api_key",
            env_vars=(),
            supports_health_check=False,
            fallback_models=(model_id,),
        )
        register_provider(profile)
        _REGISTERED_CATALOG[model_id] = dict(model_info)
        logger.info("[android_local] registered %s (%s on port %s)", model_id, backend, port)


def unregister_android_local_provider(model_id: str) -> bool:
    """Unregister an on-device provider profile."""
    from providers import _REGISTRY

    name = f"android_local_{model_id}"
    existed = name in _REGISTRY
    _REGISTRY.pop(name, None)
    _REGISTERED_CATALOG.pop(model_id, None)
    return existed


def registered_backends() -> list[dict[str, Any]]:
    """Snapshot of on-device backends currently registered in this process."""
    return [
        {
            "model_id": model_id,
            "backend": info.get("backend", "litertlm"),
            "loopback_port": info.get("loopback_port"),
            "display_name": info.get("display_name", model_id),
            "accelerator": info.get("accelerator", "cpu"),
            "supports_vision": bool(info.get("supports_vision", False)),
            "profile_name": f"android_local_{model_id}",
        }
        for model_id, info in sorted(_REGISTERED_CATALOG.items())
    ]


# =========================================================================
# Kotlin -> Python catalog plumbing
# =========================================================================
# OnDeviceBackendManager (Kotlin) owns download/verify/load and the loopback
# OpenAI-compatible server. Whenever a backend starts or stops it rewrites
# ``<files_dir>/local-model-catalog.json``; Python never probes ports or
# guesses model state — it only mirrors what Kotlin verified.


def catalog_path() -> Path | None:
    """Location of the Kotlin-written catalog file, when files dir is known."""
    files_dir = os.environ.get("HERMES_ANDROID_FILES_DIR", "")
    if not files_dir:
        return None
    return Path(files_dir) / "local-model-catalog.json"


def load_catalog_from_disk() -> dict[str, dict[str, Any]]:
    """Read verified-model entries from the Kotlin catalog file (tolerant)."""
    path = catalog_path()
    if path is None or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - a corrupt file must not boot-fail
        logger.warning("[android_local] unreadable catalog %s: %s", path, exc)
        return {}
    models = data.get("models") if isinstance(data, dict) else None
    return models if isinstance(models, dict) else {}


def sync_android_local_catalog() -> list[str]:
    """Mirror the on-disk catalog into provider registrations.

    Registers newly verified models, unregisters entries that disappeared or
    lost verification. Last-writer-wins keeps this safe to call repeatedly.
    Returns the sorted list of currently registered model ids.
    """
    disk = load_catalog_from_disk()
    register_android_local_providers(disk)
    for model_id in list(_REGISTERED_CATALOG):
        info = disk.get(model_id)
        if not isinstance(info, dict) or not info.get("verified", False):
            unregister_android_local_provider(model_id)
    return sorted(_REGISTERED_CATALOG)
