"""Skills management routes — installed skills listing + enable/disable.

Installed skills live under ``HERMES_HOME/skills``; bundled and optional
trees come from the env vars configured at boot (assets.bundled).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from aiohttp import web

from hermes_android.api.manage import error_response, hermes_home_dir, json_response


def register_routes(web_app: web.Application) -> None:
    async def list_skills(request: web.Request) -> web.Response:
        return json_response({"skills": _scan_installed_skills()})

    async def toggle_skill(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return error_response("Invalid JSON body", "INVALID_ARGUMENT", 400)
        name = str(body.get("name", "")).strip()
        enabled = bool(body.get("enabled", True))
        if not name:
            return error_response("Missing 'name'", "INVALID_ARGUMENT", 400)

        from hermes_cli.config import load_config, save_config

        config = load_config()
        skills_cfg = config.setdefault("skills", {})
        disabled = set(skills_cfg.get("disabled", []) or [])
        if enabled:
            disabled.discard(name)
            action = "enabled"
        else:
            disabled.add(name)
            action = "disabled"
        skills_cfg["disabled"] = sorted(disabled)
        save_config(config)
        # Prompt-cache safety: skill toggles apply next session.
        return json_response({"name": name, "action": action, "applies": "next_session"})

    web_app.router.add_get("/v1/manage/skills", list_skills)
    web_app.router.add_post("/v1/manage/skills/toggle", toggle_skill)


_NAME_RE = re.compile(r"^name\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_DESC_RE = re.compile(r"^description\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)


def _scan_installed_skills() -> list[dict[str, Any]]:
    from hermes_cli.config import load_config

    config = load_config()
    disabled = set((config.get("skills", {}) or {}).get("disabled", []) or [])

    roots: dict[str, Path] = {}
    try:
        roots["installed"] = hermes_home_dir() / "skills"
    except RuntimeError:
        pass
    bundled = os.environ.get("HERMES_BUNDLED_SKILLS", "").strip()
    if bundled:
        roots["bundled"] = Path(bundled)
    optional = os.environ.get("HERMES_OPTIONAL_SKILLS", "").strip()
    if optional:
        roots["optional"] = Path(optional)

    excluded = {".git", ".github", ".hub", ".archive", "__pycache__"}
    skills: dict[str, dict[str, Any]] = {}
    for origin, root in roots.items():
        if not root.is_dir():
            continue
        for skill_md in root.glob("*/*/SKILL.md"):
            category_dir = skill_md.parent.parent
            if category_dir.name in excluded or skill_md.parent.name in excluded:
                continue
            text = skill_md.read_text(encoding="utf-8", errors="replace")
            name_match = _NAME_RE.search(text)
            name = name_match.group(1).strip() if name_match else skill_md.parent.name
            desc_match = _DESC_RE.search(text)
            description = (desc_match.group(1).strip() if desc_match else "")[:120]
            entry = {
                "name": name,
                "path": str(skill_md.parent),
                "origin": origin,
                "category": category_dir.name,
                "enabled": name not in disabled,
                "description": description,
            }
            # Installed overrides bundled duplicates.
            if origin == "installed" or name not in skills:
                skills[name] = entry
    return sorted(skills.values(), key=lambda item: item["name"].lower())
