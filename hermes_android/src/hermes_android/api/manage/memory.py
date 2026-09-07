"""Memory management routes — provider status + retention info."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aiohttp import web

from hermes_android.api.manage import error_response, hermes_home_dir, json_response

# Built-in + plugin memory provider names shipped with Hermes.
KNOWN_PROVIDERS = (
    "builtin",
    "honcho",
    "mem0",
    "supermemory",
    "byterover",
    "hindsight",
    "holographic",
    "openviking",
    "retaindb",
)


def register_routes(web_app: web.Application) -> None:
    async def status(request: web.Request) -> web.Response:
        from hermes_cli.config import load_config

        config = load_config()
        memory_cfg = config.get("memory", {}) or {}
        active = str(memory_cfg.get("provider", "builtin"))
        home = hermes_home_dir()
        payload: dict[str, Any] = {
            "active_provider": active,
            "known_providers": list(KNOWN_PROVIDERS),
            "memory_dir": str(home / "memory"),
            "configured": True,
        }
        try:
            payload["memory_dir_exists"] = (home / "memory").is_dir()
        except Exception:
            payload["memory_dir_exists"] = False
        return json_response(payload)

    async def search(request: web.Request) -> web.Response:
        q = request.query.get("q", "").strip()
        if not q:
            return error_response("Missing 'q' query parameter", "INVALID_ARGUMENT", 400)
        # Memory recall is served by the agent's memory tool at run time; the
        # manage channel exposes only configuration + storage state so the UI
        # can render the browser. Search results come from SessionDB FTS on
        # /v1/manage/sessions/search.
        return json_response({"query": q, "note": "Recall executes via the agent memory tool; browse sessions via /v1/manage/sessions/search"})

    web_app.router.add_get("/v1/manage/memory/status", status)
    web_app.router.add_get("/v1/manage/memory", status)
    web_app.router.add_get("/v1/manage/memory/search", search)


def _provider_setup_state(name: str) -> dict[str, Any]:
    """Best-effort setup state for a provider (env-key presence)."""
    env_key_map = {
        "honcho": ("HONCHO_API_KEY",),
        "mem0": ("MEM0_API_KEY",),
        "supermemory": ("SUPERMEMORY_API_KEY",),
        "byterover": ("BYTEROVER_API_KEY",),
        "hindsight": ("HINDSIGHT_API_KEY",),
        "retaindb": ("RETAINDB_API_KEY",),
    }
    keys = env_key_map.get(name, ())
    configured = any(os_env.get(k) for k in keys) if (os_env := _safe_environ()) else False
    return {"provider": name, "env_keys": list(keys), "configured": bool(configured)}


def _safe_environ() -> dict:
    return dict(__import__("os").environ)
