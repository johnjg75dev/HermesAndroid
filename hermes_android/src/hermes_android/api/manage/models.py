"""Models management routes — active model, on-device provider registration state."""

from __future__ import annotations

from typing import Any

from aiohttp import web

from hermes_android.api.manage import error_response, json_response


def register_routes(web_app: web.Application) -> None:
    async def get_models(request: web.Request) -> web.Response:
        from hermes_cli.config import load_config

        config = load_config()
        return json_response({
            "model": config.get("model", ""),
            "provider": config.get("provider", ""),
            "base_url": config.get("base_url", ""),
            "fallback_model": (config.get("agent", {}) or {}).get("fallback_model", ""),
            "on_device": _on_device_state(),
        })

    async def set_model(request: web.Request) -> web.Response:
        from hermes_cli.config import load_config, save_config

        try:
            body = await request.json()
        except Exception:
            return error_response("Invalid JSON body", "INVALID_ARGUMENT", 400)
        model = str(body.get("model", "")).strip()
        if not model:
            return error_response("Missing 'model'", "INVALID_ARGUMENT", 400)
        config = load_config()
        if body.get("provider"):
            config["provider"] = str(body["provider"])
        if body.get("base_url") is not None:
            config["base_url"] = str(body["base_url"])
        config["model"] = model
        save_config(config)
        # Model switches change the cached system prompt → next session only.
        return json_response({"model": model, "applies": "next_session"})

    web_app.router.add_get("/v1/manage/models", get_models)
    web_app.router.add_post("/v1/manage/models/active", set_model)


def _on_device_state() -> dict[str, Any]:
    """Local-model backend availability as reported by the android_local hook.

    Re-syncs from the Kotlin-written catalog file first so a model started or
    stopped after boot is reflected without an app restart.
    """
    try:
        from hermes_android.providers.android_local import (
            registered_backends,
            sync_android_local_catalog,
        )

        sync_android_local_catalog()
        return {"backends": registered_backends()}
    except Exception:
        return {"backends": [], "note": "android_local providers not loaded"}
