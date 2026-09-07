"""MCP management routes — server list from HERMES_HOME/mcp/mcp_config.json."""

from __future__ import annotations

import json
from typing import Any

from aiohttp import web

from hermes_android.api.manage import error_response, hermes_home_dir, json_response


def _config_path():
    return hermes_home_dir() / "mcp" / "mcp_config.json"


def _load_servers() -> dict[str, Any]:
    path = _config_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    servers = data.get("mcpServers") or data.get("mcp_servers") or {}
    return servers if isinstance(servers, dict) else {}


def _save_servers(servers: dict[str, Any]) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {}
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
    payload["mcpServers"] = servers
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def register_routes(web_app: web.Application) -> None:
    async def list_servers(request: web.Request) -> web.Response:
        servers = []
        for name, raw in _load_servers().items():
            entry = dict(raw) if isinstance(raw, dict) else {"value": str(raw)}
            servers.append({"name": name, **entry})
        return json_response({"servers": servers})

    async def add_server(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return error_response("Invalid JSON body", "INVALID_ARGUMENT", 400)
        name = str(body.get("name", "")).strip()
        if not name:
            return error_response("Missing 'name'", "INVALID_ARGUMENT", 400)
        servers = _load_servers()
        servers[name] = {k: v for k, v in body.items() if k != "name"}
        _save_servers(servers)
        # MCP registration happens at boot; config changes apply next session.
        return json_response({"name": name, "applies": "next_session"}, status=201)

    async def test_server(request: web.Request) -> web.Response:
        name = request.match_info["name"]
        raw = _load_servers().get(name)
        if raw is None:
            return error_response(f"MCP server not found: {name}", "MCP_SERVER_NOT_FOUND", 404)
        # Structural validation only — live spawn happens through the agent.
        issues = []
        transport = str((raw or {}).get("transport", "stdio")).lower() if isinstance(raw, dict) else "stdio"
        if transport == "stdio" and not (raw or {}).get("command"):
            issues.append("stdio transport requires 'command'")
        if transport in {"sse", "http", "streamable_http"} and not (raw or {}).get("url"):
            issues.append(f"{transport} transport requires 'url'")
        return json_response({
            "name": name,
            "valid": not issues,
            "issues": issues,
        })

    async def remove_server(request: web.Request) -> web.Response:
        name = request.match_info["name"]
        servers = _load_servers()
        if name not in servers:
            return error_response(f"MCP server not found: {name}", "MCP_SERVER_NOT_FOUND", 404)
        del servers[name]
        _save_servers(servers)
        return json_response({"removed": True, "name": name})

    web_app.router.add_get("/v1/manage/mcp", list_servers)
    web_app.router.add_post("/v1/manage/mcp", add_server)
    web_app.router.add_get("/v1/manage/mcp/{name}/test", test_server)
    web_app.router.add_delete("/v1/manage/mcp/{name}", remove_server)
