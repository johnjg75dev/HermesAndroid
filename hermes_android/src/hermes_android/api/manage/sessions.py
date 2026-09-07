"""Sessions management routes — SessionDB is the only conversation store.

Endpoints:
  GET    /v1/manage/sessions?limit&offset&source     list_sessions_rich
  GET    /v1/manage/sessions/search?q=...            FTS5 search_messages
  GET    /v1/manage/sessions/{id}                    session row (+messages)
  GET    /v1/manage/sessions/{id}/export             full export payload
  POST   /v1/manage/sessions/{id}/branch             copy messages into a new session
  PATCH  /v1/manage/sessions/{id}                    {title}
  DELETE /v1/manage/sessions/{id}
"""

from __future__ import annotations

import json
import logging
from typing import Any

from aiohttp import web

from hermes_android.api.manage import error_response, json_response

logger = logging.getLogger(__name__)


def _open_db():
    from hermes_state import SessionDB

    return SessionDB()


def register_routes(web_app: web.Application) -> None:
    async def list_sessions(request: web.Request) -> web.Response:
        limit = max(1, min(int(request.query.get("limit", "50")), 200))
        offset = max(0, int(request.query.get("offset", "0")))
        source = request.query.get("source") or None
        db = _open_db()
        try:
            rows = db.list_sessions_rich(
                source=source,
                limit=limit,
                offset=offset,
                order_by_last_active=True,
            )
            total = db.session_count()
        finally:
            db.close()
        return json_response({"sessions": rows, "total": total, "limit": limit, "offset": offset})

    async def search(request: web.Request) -> web.Response:
        q = request.query.get("q", "").strip()
        if not q:
            return error_response("Missing 'q' query parameter", "INVALID_ARGUMENT", 400)
        limit = max(1, min(int(request.query.get("limit", "20")), 100))
        db = _open_db()
        try:
            results = db.search_messages(q, limit=limit)
        finally:
            db.close()
        return json_response({"results": results, "query": q, "limit": limit})

    async def get_session(request: web.Request) -> web.Response:
        session_id = request.match_info["session_id"]
        include_messages = request.query.get("with_messages", "0") in {"1", "true"}
        db = _open_db()
        try:
            resolved = db.resolve_session_id(session_id)
            if not resolved:
                return error_response(f"Session not found: {session_id}", "SESSION_NOT_FOUND", 404)
            row = db.get_session(resolved)
            if row is None:
                return error_response(f"Session not found: {session_id}", "SESSION_NOT_FOUND", 404)
            if isinstance(row, str):
                try:
                    row = json.loads(row)
                except Exception:
                    pass
            payload: dict[str, Any] = {"session": row}
            if include_messages:
                payload["messages"] = db.get_messages(resolved)
            return json_response(payload)
        finally:
            db.close()

    async def export_session(request: web.Request) -> web.Response:
        session_id = request.match_info["session_id"]
        db = _open_db()
        try:
            resolved = db.resolve_session_id(session_id)
            exported = db.export_session(resolved) if resolved else None
            if not exported:
                return error_response(f"Session not found: {session_id}", "SESSION_NOT_FOUND", 404)
            if isinstance(exported, str):
                try:
                    exported = json.loads(exported)
                except Exception:
                    pass
            return json_response({"export": exported})
        finally:
            db.close()

    async def branch_session(request: web.Request) -> web.Response:
        session_id = request.match_info["session_id"]
        try:
            body = await request.json()
        except Exception:
            body = {}
        title = str(body.get("title") or "").strip() or None
        db = _open_db()
        try:
            resolved = db.resolve_session_id(session_id)
            if not resolved:
                return error_response(f"Session not found: {session_id}", "SESSION_NOT_FOUND", 404)
            source_row = db.get_session(resolved) or {}
            source_meta = (
                source_row.get("meta")
                if isinstance(source_row, dict) and isinstance(source_row.get("meta"), dict)
                else {}
            )
            new_id = f"branch-{resolved[:24]}-{__import__('uuid').uuid4().hex[:10]}"
            created = db.create_session(new_id, source=str(source_meta.get("source", "api_server")))
            messages = db.get_messages(resolved)
            for message in messages:
                db.append_message(new_id, message.get("role", ""), message.get("content", ""))
            if title:
                db.set_session_title(new_id, title)
            del created
            return json_response(
                {"session_id": new_id, "parent_session_id": resolved, "message_count": len(messages)},
                status=201,
            )
        finally:
            db.close()

    async def rename_session(request: web.Request) -> web.Response:
        session_id = request.match_info["session_id"]
        try:
            body = await request.json()
        except Exception:
            return error_response("Invalid JSON body", "INVALID_ARGUMENT", 400)
        title = str(body.get("title", "")).strip()
        if not title:
            return error_response("Missing 'title'", "INVALID_ARGUMENT", 400)
        db = _open_db()
        try:
            resolved = db.resolve_session_id(session_id) or session_id
            ok = db.set_session_title(resolved, title)
            if not ok:
                return error_response(f"Session not found: {session_id}", "SESSION_NOT_FOUND", 404)
            return json_response({"session_id": resolved, "title": title})
        finally:
            db.close()

    async def delete_session(request: web.Request) -> web.Response:
        session_id = request.match_info["session_id"]
        db = _open_db()
        try:
            resolved = db.resolve_session_id(session_id) or session_id
            deleted = db.delete_session(resolved)
            if not deleted:
                return error_response(f"Session not found: {session_id}", "SESSION_NOT_FOUND", 404)
            return json_response({"deleted": True, "session_id": resolved})
        finally:
            db.close()

    web_app.router.add_get("/v1/manage/sessions/search", search)
    web_app.router.add_get("/v1/manage/sessions/{session_id}/export", export_session)
    web_app.router.add_post("/v1/manage/sessions/{session_id}/branch", branch_session)
    web_app.router.add_patch("/v1/manage/sessions/{session_id}", rename_session)
    web_app.router.add_delete("/v1/manage/sessions/{session_id}", delete_session)
    web_app.router.add_get("/v1/manage/sessions/{session_id}", get_session)
    web_app.router.add_get("/v1/manage/sessions", list_sessions)
