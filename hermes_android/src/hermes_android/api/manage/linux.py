"""Linux subsystem management routes — state + health readout."""

from __future__ import annotations

import os

from aiohttp import web

from hermes_android.api.manage import json_response


def register_routes(web_app: web.Application) -> None:
    async def linux_status(request: web.Request) -> web.Response:
        return json_response(_collect())

    async def health(request: web.Request) -> web.Response:
        payload = _collect()
        payload["health"] = _health_from_state(payload.get("state") or {})
        return json_response(payload)

    web_app.router.add_get("/v1/manage/linux", linux_status)
    web_app.router.add_get("/v1/manage/linux/health", health)


def _files_dir():
    raw = os.environ.get("HERMES_ANDROID_FILES_DIR", "").strip()
    if not raw:
        return None
    from pathlib import Path

    path = Path(raw).expanduser().resolve()
    return path if path.is_dir() else None


def _collect() -> dict:
    files_dir = _files_dir()
    if files_dir is None:
        return {
            "available": False,
            "note": "HERMES_ANDROID_FILES_DIR not set; Linux subsystem state unknown",
            "state": None,
            "ssh_backend": probe_ssh_backend(),
        }
    from hermes_android.linux.state import LinuxStateManager

    state = LinuxStateManager(files_dir).load()
    if state is None:
        return {
            "available": False,
            "state": None,
            "note": "No persisted subsystem state",
            "ssh_backend": probe_ssh_backend(),
        }
    from dataclasses import asdict

    return {
        "available": bool(state.enabled),
        "state": asdict(state),
        "ssh_backend": probe_ssh_backend(),
    }


_SSH_BACKEND_CACHE: str | None = None


def probe_ssh_backend() -> str:
    """Best-effort SSH backend detection per locked decision 3.

    Probes asyncssh first, then paramiko; returns "none" when neither wheel
    ships in this interpreter so clients can hide the SSH path on Android.
    Result is cached — wheel availability never changes mid-process.
    """
    global _SSH_BACKEND_CACHE
    if _SSH_BACKEND_CACHE is not None:
        return _SSH_BACKEND_CACHE
    for module in ("asyncssh", "paramiko"):
        try:
            __import__(module)
            _SSH_BACKEND_CACHE = module
            return module
        except Exception:
            continue
    _SSH_BACKEND_CACHE = "none"
    return "none"


def _health_from_state(state: dict) -> str | None:
    health = state.get("health")
    return str(health) if health else None
