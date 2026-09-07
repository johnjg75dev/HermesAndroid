"""Config management routes — read/write runtime config.yaml.

POST /v1/manage/config applies a shallow patch. Responses carry an
``applies`` marker per the bridge contract: display.* keys apply now,
everything else takes effect next session (prompt-cache safety).
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from aiohttp import web

from hermes_android.api.manage import error_response, json_response

_IMMEDIATE_PREFIXES = ("display.",)


def register_routes(web_app: web.Application) -> None:
    async def get_config(request: web.Request) -> web.Response:
        from hermes_cli.config import load_config

        config = load_config()
        return json_response({"config": config, "applies": "next_session"})

    async def patch_config(request: web.Request) -> web.Response:
        from hermes_cli.config import load_config, save_config

        try:
            body = await request.json()
        except Exception:
            return error_response("Invalid JSON body", "INVALID_ARGUMENT", 400)
        patch = body.get("patch") if isinstance(body.get("patch"), dict) else body
        if not isinstance(patch, dict) or not patch:
            return error_response("Missing 'patch' object", "INVALID_ARGUMENT", 400)

        config = load_config()
        merged = deepcopy(config)
        immediate: list[str] = []
        deferred: list[str] = []
        for key, value in patch.items():
            _deep_set(merged, key, value)
            if key.startswith(_IMMEDIATE_PREFIXES):
                immediate.append(key)
            else:
                deferred.append(key)

        save_config(merged)
        return json_response({
            "config": merged,
            "applies": "now" if not deferred else "next_session",
            "applies_now_keys": immediate,
            "applies_next_session_keys": deferred,
        })

    web_app.router.add_get("/v1/manage/config", get_config)
    web_app.router.add_post("/v1/manage/config", patch_config)
    web_app.router.add_patch("/v1/manage/config", patch_config)


def _deep_set(target: dict[str, Any], dotted_key: str, value: Any) -> None:
    parts = dotted_key.split(".")
    node = target
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[parts[-1]] = value
