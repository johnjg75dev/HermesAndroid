"""Plugins management routes — best-effort manifest listing."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from aiohttp import web

from hermes_android.api.manage import hermes_home_dir, json_response


def register_routes(web_app: web.Application) -> None:
    async def list_plugins(request: web.Request) -> web.Response:
        return json_response({"plugins": _scan_plugin_dirs()})

    web_app.router.add_get("/v1/manage/plugins", list_plugins)


def _scan_plugin_dirs() -> list[dict[str, Any]]:
    """Read plugin.yaml manifests without importing plugin code."""
    roots = []
    try:
        roots.append(hermes_home_dir() / "plugins")
    except RuntimeError:
        pass

    # Bundled repo plugins (present in the wheel tree on device).
    try:
        from hermes_android.python_path import prefer_hermes_package_root  # noqa: F401

        import importlib.util

        spec = importlib.util.find_spec("hermes_cli")
        if spec and spec.origin:
            repo_root = Path(spec.origin).resolve().parent.parent
            roots.append(repo_root / "plugins")
    except Exception:
        pass

    plugins: dict[str, dict[str, Any]] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for manifest_path in root.glob("*/plugin.yaml"):
            name = manifest_path.parent.name
            entry: dict[str, Any] = {"name": name, "path": str(manifest_path.parent)}
            try:
                text = manifest_path.read_text(encoding="utf-8", errors="replace")
                for line in text.splitlines():
                    if line.startswith(("name:", "version:", "description:", "kind:")):
                        key, _, value = line.partition(":")
                        entry[key.strip()] = value.strip().strip("'\"")
            except Exception as exc:
                entry["manifest_error"] = str(exc)
            # User plugins override bundled entries with the same name.
            if "plugins" in root.parts and root.parts[-1] == "plugins" and root.is_relative_to(hermes_home_dir_safe()):
                entry["source"] = "user"
            else:
                entry["source"] = "bundled"
            if entry["source"] == "user" or name not in plugins:
                plugins[name] = entry
    return sorted(plugins.values(), key=lambda item: item["name"])


def hermes_home_dir_safe() -> Path | None:
    try:
        return hermes_home_dir()
    except Exception:
        env = os.environ.get("HERMES_HOME", "").strip()
        return Path(env) if env else None
