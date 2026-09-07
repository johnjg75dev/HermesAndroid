"""Profiles management routes — HERMES_HOME isolation via hermes_android.profile."""

from __future__ import annotations

import os

from aiohttp import web

from hermes_android.api.manage import error_response, json_response


def _manager():
    from hermes_android.profile.manager import ProfileManager

    files_dir = os.environ.get("HERMES_ANDROID_FILES_DIR", "") or None
    return ProfileManager(files_dir) if files_dir else ProfileManager()


def register_routes(web_app: web.Application) -> None:
    async def list_profiles(request: web.Request) -> web.Response:
        mgr = _manager()
        return json_response({
            "profiles": mgr.list_profiles(),
            "active": mgr.get_active_profile_name(),
            "hermes_home": os.environ.get("HERMES_HOME", ""),
        })

    async def create_profile(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return error_response("Invalid JSON body", "INVALID_ARGUMENT", 400)
        name = str(body.get("name", "")).strip()
        if not name:
            return error_response("Missing 'name'", "INVALID_ARGUMENT", 400)
        mgr = _manager()
        try:
            profile_dir = mgr.create_profile(name)
        except Exception as exc:
            return error_response(str(exc), "PROFILE_SWITCH_FAILED", 409)
        return json_response({"name": name, "path": str(profile_dir)}, status=201)

    async def switch_profile(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return error_response("Invalid JSON body", "INVALID_ARGUMENT", 400)
        name = str(body.get("name", "")).strip()
        if not name:
            return error_response("Missing 'name'", "INVALID_ARGUMENT", 400)
        mgr = _manager()
        try:
            mgr.set_active_profile(name)
        except Exception as exc:
            return error_response(str(exc), "PROFILE_NOT_FOUND", 404)
        # Profile switch = restart handshake (Kotlin re-starts the runtime).
        return json_response({"name": name, "applies": "restart_required"})

    async def delete_profile(request: web.Request) -> web.Response:
        name = request.match_info["name"]
        mgr = _manager()
        try:
            mgr.delete_profile(name)
        except Exception as exc:
            code = "PROFILE_SWITCH_FAILED"
            if "does not exist" in str(exc):
                code = "PROFILE_NOT_FOUND"
            return error_response(str(exc), code, 409)
        return json_response({"deleted": True, "name": name})

    web_app.router.add_get("/v1/manage/profiles", list_profiles)
    web_app.router.add_post("/v1/manage/profiles", create_profile)
    web_app.router.add_post("/v1/manage/profiles/active", switch_profile)
    web_app.router.add_delete("/v1/manage/profiles/{name}", delete_profile)
