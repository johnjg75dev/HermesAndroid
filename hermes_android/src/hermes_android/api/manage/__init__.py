"""Manage API — loopback management channel mounted on the agent's aiohttp app.

Every response carries ``bridge_version`` (see hermes_android.api.versioning).
Modules expose ``register_routes(web_app)`` and use the helpers below so all
endpoints share JSON/error conventions.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable

from aiohttp import web

from hermes_android.api.versioning import BRIDGE_VERSION

logger = logging.getLogger(__name__)

__all__ = [
    "mount_manage_routes",
    "json_response",
    "error_response",
    "manage_route",
    "hermes_home_dir",
]

MODULES = (
    "sessions",
    "config",
    "system",
    "skills",
    "cron",
    "kanban",
    "memory",
    "providers",
    "models",
    "mcp",
    "profiles",
    "plugins",
    "linux",
    "device",
    "migration",
    "insights",
    "files",
)


def mount_manage_routes(web_app: web.Application) -> None:
    """Register every manage module's routes on the given aiohttp app."""
    import importlib

    for name in MODULES:
        module = importlib.import_module(f"hermes_android.api.manage.{name}")
        register = getattr(module, "register_routes", None)
        if callable(register):
            try:
                register(web_app)
            except Exception:
                logger.exception("[manage] failed to register %s routes", name)


def json_response(payload: dict[str, Any], *, status: int = 200) -> web.Response:
    body = {"bridge_version": BRIDGE_VERSION, **payload}
    return web.json_response(body, status=status)


def error_response(message: str, code: str, status: int) -> web.Response:
    return json_response({"error": message, "code": code}, status=status)


def manage_route(
    method: str,
    path: str,
) -> Callable[
    [Callable[[web.Request], Awaitable[dict[str, Any]]]],
    Callable[[web.Request], Awaitable[web.Response]],
]:
    """Decorator turning an async payload handler into a registered route.

    The wrapped handler returns a plain dict; this wrapper attaches
    bridge_version and converts exceptions to typed JSON errors.
    """

    def decorator(fn: Callable[[web.Request], Awaitable[dict[str, Any]]]):
        async def _handler(request: web.Request) -> web.Response:
            try:
                payload = await fn(request)
                status = int(payload.pop("_status", 200))
                return json_response(payload, status=status)
            except web.HTTPException:
                raise
            except Exception as exc:  # noqa: BLE001 - uniform error envelope
                logger.exception("[manage] %s %s failed", method, path)
                from hermes_android.errors import HermesError

                if isinstance(exc, HermesError):
                    code = getattr(getattr(exc, "code", None), "code", None) or getattr(
                        exc, "code", "INTERNAL_ERROR"
                    )
                    if not isinstance(code, str):
                        code = getattr(code, "value", "INTERNAL_ERROR")
                    return error_response(str(exc), code, 500)
                return error_response(str(exc), "INTERNAL_ERROR", 500)

        _handler.__name__ = f"manage_{method.lower()}_{path.strip('/').replace('/', '_')}"
        _handler.manage_path = path
        return _handler

    return decorator


def hermes_home_dir():
    """Resolve HERMES_HOME for manage handlers."""
    import os
    from pathlib import Path

    raw = os.environ.get("HERMES_HOME", "").strip()
    if not raw:
        raise RuntimeError("HERMES_HOME is not set")
    return Path(raw).expanduser().resolve()
