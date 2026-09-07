"""Workspace file management routes (M24).

All paths are jailed to ``<hermes_home>/workspace`` — traversal outside the
workspace is rejected fail-closed. Read-only listing/reading plus text writes
for scratch files; binary artifacts stay with dedicated tools.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from aiohttp import web

from hermes_android.api.manage import error_response, json_response

logger = logging.getLogger(__name__)

_MAX_READ_CHARS = 200_000
_MAX_LIST_ENTRIES = 500


def register_routes(web_app: web.Application) -> None:
    web_app.router.add_get("/v1/manage/files/list", _list)
    web_app.router.add_get("/v1/manage/files/read", _read)
    web_app.router.add_post("/v1/manage/files/write", _write)


def _workspace_root() -> Path:
    root = Path(os.environ.get("HERMES_HOME", "")) / "workspace"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _safe_resolve(root: Path, relative: str) -> Path | None:
    candidate = (root / relative.lstrip("/\\")).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def _relative_of(root: Path, candidate: Path) -> str:
    return candidate.relative_to(root).as_posix()


async def _list(request: web.Request) -> web.Response:
    root = _workspace_root()
    relative = request.query.get("path", "")
    target = _safe_resolve(root, relative)
    if target is None:
        return error_response("Path escapes the workspace", "INVALID_ARGUMENT", 400)
    if not target.exists():
        return json_response({"entries": [], "path": _relative_of(root, target)})
    if target.is_file():
        target = target.parent

    entries: list[dict[str, Any]] = []
    try:
        for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if len(entries) >= _MAX_LIST_ENTRIES:
                break
            stat = child.stat()
            entries.append({
                "name": child.name,
                "is_directory": child.is_dir(),
                "size_bytes": stat.st_size if child.is_file() else 0,
                "modified_epoch_ms": int(stat.st_mtime * 1000),
            })
    except OSError as exc:
        return error_response(f"List failed: {exc}", "FILE_ERROR", 500)
    return json_response({
        "entries": entries,
        "path": _relative_of(root, target),
    })


async def _read(request: web.Request) -> web.Response:
    root = _workspace_root()
    relative = request.query.get("path", "")
    target = _safe_resolve(root, relative)
    if target is None:
        return error_response("Path escapes the workspace", "INVALID_ARGUMENT", 400)
    if not target.is_file():
        return error_response("Not a file", "NOT_FOUND", 404)
    try:
        content = target.read_text(encoding="utf-8", errors="replace")[:_MAX_READ_CHARS]
    except OSError as exc:
        return error_response(f"Read failed: {exc}", "FILE_ERROR", 500)
    truncated = target.stat().st_size > _MAX_READ_CHARS
    return json_response({
        "path": _relative_of(root, target),
        "content": content,
        "truncated": truncated,
    })


async def _write(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return error_response("Invalid JSON body", "INVALID_ARGUMENT", 400)
    root = _workspace_root()
    relative = str(body.get("path", ""))
    content = body.get("content", "")
    if not relative:
        return error_response("Missing 'path'", "INVALID_ARGUMENT", 400)
    target = _safe_resolve(root, relative)
    if target is None:
        return error_response("Path escapes the workspace", "INVALID_ARGUMENT", 400)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(content), encoding="utf-8")
    except OSError as exc:
        return error_response(f"Write failed: {exc}", "FILE_ERROR", 500)
    return json_response({"path": _relative_of(root, target), "written": True})
