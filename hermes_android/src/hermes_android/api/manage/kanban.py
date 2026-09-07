"""Kanban management routes — human-first board control over hermes_cli.kanban_db.

All operations go through ``hermes_cli.kanban_db`` (the same store the CLI and
dispatcher use); this channel adds no second board implementation.
"""

from __future__ import annotations

from typing import Any

from aiohttp import web

from hermes_android.api.manage import error_response, json_response


def register_routes(web_app: web.Application) -> None:
    async def list_boards(request: web.Request) -> web.Response:
        from hermes_cli import kanban_db as kb

        return json_response({"boards": kb.list_boards(), "current": kb.get_current_board()})

    async def create_board(request: web.Request) -> web.Response:
        from hermes_cli import kanban_db as kb

        try:
            body = await request.json()
        except Exception:
            return error_response("Invalid JSON body", "INVALID_ARGUMENT", 400)
        name = str(body.get("name", "")).strip()
        if not name:
            return error_response("Missing 'name'", "INVALID_ARGUMENT", 400)
        board = kb.create_board(name)
        return json_response({"board": _plain(board)}, status=201)

    async def list_tasks(request: web.Request) -> web.Response:
        from hermes_cli import kanban_db as kb

        current = kb.get_current_board()
        if not current:
            return json_response({
                "tasks": [],
                "note": "No kanban board configured — run `hermes kanban init`",
            })
        conn = kb.connect(board=current)
        try:
            tasks = kb.list_tasks(conn)
        finally:
            conn.close()
        return json_response({"tasks": [_plain(t) for t in tasks], "board": current})

    async def create_task(request: web.Request) -> web.Response:
        from hermes_cli import kanban_db as kb

        current = kb.get_current_board()
        if not current:
            return error_response(
                "No kanban board configured — create one with the boards endpoint",
                "KANBAN_NO_BOARD",
                409,
            )
        try:
            body = await request.json()
        except Exception:
            return error_response("Invalid JSON body", "INVALID_ARGUMENT", 400)
        title = str(body.get("title", "")).strip()
        if not title:
            return error_response("Missing 'title'", "INVALID_ARGUMENT", 400)
        parents = body.get("parent") or body.get("parents") or ()
        if isinstance(parents, str):
            parents = (parents,)
        conn = kb.connect(board=current)
        try:
            task_id = kb.create_task(
                conn,
                title=title,
                body=str(body.get("description") or "") or None,
                assignee=body.get("assignee"),
                parents=tuple(parents),
            )
            task = kb.get_task(conn, task_id)
        finally:
            conn.close()
        return json_response({"task": _plain(task)}, status=201)

    async def get_task(request: web.Request) -> web.Response:
        from hermes_cli import kanban_db as kb

        task_id = request.match_info["task_id"]
        conn = kb.connect()
        try:
            task = kb.get_task(conn, task_id)
            if not task:
                return error_response(f"Task not found: {task_id}", "KANBAN_TASK_NOT_FOUND", 404)
            comments = kb.list_comments(conn, task_id)
        finally:
            conn.close()
        return json_response({"task": _plain(task), "comments": [_plain(c) for c in comments]})

    async def comment_task(request: web.Request) -> web.Response:
        from hermes_cli import kanban_db as kb

        task_id = request.match_info["task_id"]
        try:
            body = await request.json()
        except Exception:
            return error_response("Invalid JSON body", "INVALID_ARGUMENT", 400)
        text = str(body.get("text", "")).strip()
        author = str(body.get("author", "user")).strip() or "user"
        if not text:
            return error_response("Missing 'text'", "INVALID_ARGUMENT", 400)
        conn = kb.connect()
        try:
            count = kb.add_comment(conn, task_id, author=author, body=text)
        finally:
            conn.close()
        if not count:
            return error_response(f"Task not found: {task_id}", "KANBAN_TASK_NOT_FOUND", 404)
        return json_response({"commented": True, "task_id": task_id})

    async def complete_task(request: web.Request) -> web.Response:
        from hermes_cli import kanban_db as kb

        task_id = request.match_info["task_id"]
        result_summary = ""
        try:
            body = await request.json()
            result_summary = str(body.get("summary", "") or "")
        except Exception:
            pass
        conn = kb.connect()
        try:
            ok = kb.complete_task(conn, task_id, summary=result_summary or None)
        finally:
            conn.close()
        if not ok:
            return error_response(
                f"Task not found or not completable: {task_id}",
                "KANBAN_TASK_NOT_FOUND",
                404,
            )
        return json_response({"completed": True, "task_id": task_id})

    async def block_task(request: web.Request) -> web.Response:
        from hermes_cli import kanban_db as kb

        task_id = request.match_info["task_id"]
        reason = ""
        try:
            body = await request.json()
            reason = str(body.get("reason", ""))
        except Exception:
            pass
        conn = kb.connect()
        try:
            ok = kb.block_task(conn, task_id, reason=reason or None)
        finally:
            conn.close()
        if not ok:
            return error_response(f"Task not found: {task_id}", "KANBAN_TASK_NOT_FOUND", 404)
        return json_response({"blocked": True, "task_id": task_id})

    async def unblock_task(request: web.Request) -> web.Response:
        from hermes_cli import kanban_db as kb

        task_id = request.match_info["task_id"]
        conn = kb.connect()
        try:
            ok = kb.unblock_task(conn, task_id)
        finally:
            conn.close()
        if not ok:
            return error_response(f"Task not found: {task_id}", "KANBAN_TASK_NOT_FOUND", 404)
        return json_response({"unblocked": True, "task_id": task_id})

    web_app.router.add_post("/v1/manage/kanban/boards", create_board)
    web_app.router.add_get("/v1/manage/kanban/boards", list_boards)
    web_app.router.add_post("/v1/manage/kanban/tasks/{task_id}/complete", complete_task)
    web_app.router.add_post("/v1/manage/kanban/tasks/{task_id}/block", block_task)
    web_app.router.add_post("/v1/manage/kanban/tasks/{task_id}/unblock", unblock_task)
    web_app.router.add_post("/v1/manage/kanban/tasks/{task_id}/comment", comment_task)
    web_app.router.add_get("/v1/manage/kanban/tasks/{task_id}", get_task)
    web_app.router.add_post("/v1/manage/kanban/tasks", create_task)
    web_app.router.add_get("/v1/manage/kanban/tasks", list_tasks)


def _plain(obj: Any) -> Any:
    """Normalize sqlite Row / dataclass / dict records into plain dicts."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "_asdict"):
        return dict(obj._asdict())  # type: ignore[attr-defined]
    keys = getattr(obj, "keys", None)
    if callable(keys):
        try:
            return {k: obj[k] for k in keys()}
        except Exception:
            pass
    if hasattr(obj, "__dict__"):
        return dict(vars(obj))
    return {"repr": str(obj)}
