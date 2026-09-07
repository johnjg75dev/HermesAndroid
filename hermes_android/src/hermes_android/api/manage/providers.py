"""Providers management routes — configured provider/API-key presence."""

from __future__ import annotations

import os
from typing import Any

from aiohttp import web

from hermes_android.api.manage import error_response, json_response

# provider → env keys that count as "configured" (first match wins).
PROVIDER_ENV_KEYS: dict[str, tuple[str, ...]] = {
    "openrouter": ("OPENROUTER_API_KEY",),
    "nous": ("NOUS_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "gemini": ("GOOGLE_API_KEY",),
    "groq": ("GROQ_API_KEY",),
    "deepseek": ("DEEPSEEK_API_KEY",),
    "alibaba": ("DASHSCOPE_API_KEY",),
    "zai": ("GLM_API_KEY", "ZAI_API_KEY"),
    "xai": ("XAI_API_KEY",),
}


def register_routes(web_app: web.Application) -> None:
    async def list_providers(request: web.Request) -> web.Response:
        from hermes_cli.config import load_config

        config = load_config()
        active_provider = str(config.get("provider", "") or "")
        providers = []
        for name, env_keys in PROVIDER_ENV_KEYS.items():
            present = any((os.environ.get(k) or "").strip() for k in env_keys)
            providers.append({
                "name": name,
                "env_key": env_keys[0],
                "configured": bool(present),
                "active": name == active_provider,
            })
        return json_response({"providers": providers, "active_provider": active_provider})

    async def set_active(request: web.Request) -> web.Response:
        from hermes_cli.config import load_config, save_config

        try:
            body = await request.json()
        except Exception:
            return error_response("Invalid JSON body", "INVALID_ARGUMENT", 400)
        provider = str(body.get("provider", "")).strip()
        model = str(body.get("model", "")).strip()
        base_url = str(body.get("base_url", "")).strip()
        if not provider:
            return error_response("Missing 'provider'", "INVALID_ARGUMENT", 400)
        config = load_config()
        config["provider"] = provider
        if model:
            config["model"] = model
        config["base_url"] = base_url
        save_config(config)
        # Model/provider switches are cache-relevant → next session.
        return json_response({"provider": provider, "applies": "next_session"})

    web_app.router.add_get("/v1/manage/providers", list_providers)
    web_app.router.add_post("/v1/manage/providers/active", set_active)
