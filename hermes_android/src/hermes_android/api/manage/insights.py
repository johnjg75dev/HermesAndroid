"""Insights routes (M22) — runs/tokens/cost aggregation over SessionDB.

Read-only SQL over the session store; no writes, no schema changes. All
figures come from recorded sessions — nothing is extrapolated.
"""

from __future__ import annotations

import datetime as _dt
import logging
import sqlite3
from typing import Any

from aiohttp import web

from hermes_android.api.manage import json_response

logger = logging.getLogger(__name__)

_DAY_WINDOW = 14  # days of daily history


def register_routes(web_app: web.Application) -> None:
    async def insights(request: web.Request) -> web.Response:
        return json_response(_collect())

    web_app.router.add_get("/v1/manage/insights", insights)


def _db() -> sqlite3.Connection:
    """Read-only connection to the session store.

    SessionDB keeps its handle private; opening the same WAL database in
    read-only mode is safe for concurrent readers and cannot mutate state.
    """
    from hermes_state import DEFAULT_DB_PATH

    path = str(DEFAULT_DB_PATH)
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
    return conn


def _collect() -> dict[str, Any]:
    try:
        conn = _db()
    except Exception as exc:
        logger.warning("[insights] db unavailable: %s", exc)
        return {"available": False, "note": "Session store unavailable"}

    conn.row_factory = sqlite3.Row
    out: dict[str, Any] = {"available": True}
    try:
        totals = _totals(conn)
        out["daily"] = _daily(conn)
        out["models"] = _by_model(conn)
        # Flatten totals so clients read scalar keys directly.
        out.update(totals)
    except Exception as exc:
        logger.warning("[insights] aggregation failed: %s", exc)
        out["available"] = False
        out["note"] = f"aggregation failed: {exc}"
    finally:
        conn.close()
    return out


def _totals(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT COUNT(*) AS runs,
               COALESCE(SUM(message_count), 0) AS messages,
               COALESCE(SUM(tool_call_count), 0) AS tool_calls,
               COALESCE(SUM(input_tokens), 0) AS input_tokens,
               COALESCE(SUM(output_tokens), 0) AS output_tokens,
               COALESCE(SUM(cache_read_tokens), 0) AS cache_read_tokens,
               COALESCE(SUM(cache_write_tokens), 0) AS cache_write_tokens,
               COALESCE(SUM(reasoning_tokens), 0) AS reasoning_tokens,
               COALESCE(SUM(COALESCE(actual_cost_usd, estimated_cost_usd)), 0) AS cost_usd
        FROM sessions
        WHERE source != 'cron'
        """
    ).fetchone()
    return dict(row) if row else {}


def _daily(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    cutoff = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=_DAY_WINDOW)).timestamp()
    rows = conn.execute(
        """
        SELECT DATE(started_at, 'unixepoch') AS day,
               COUNT(*) AS runs,
               COALESCE(SUM(input_tokens + output_tokens), 0) AS tokens,
               COALESCE(SUM(COALESCE(actual_cost_usd, estimated_cost_usd)), 0) AS cost_usd
        FROM sessions
        WHERE started_at >= ? AND source != 'cron'
        GROUP BY day ORDER BY day ASC
        """,
        (cutoff,),
    ).fetchall()
    by_day = {r["day"]: dict(r) for r in rows}
    # Fill the window so the UI renders gaps instead of compressing the axis.
    today = _dt.datetime.now(_dt.timezone.utc).date()
    filled = []
    for offset in range(_DAY_WINDOW - 1, -1, -1):
        day = (today - _dt.timedelta(days=offset)).isoformat()
        entry = by_day.get(day) or {"day": day, "runs": 0, "tokens": 0, "cost_usd": 0.0}
        filled.append(entry)
    return filled


def _by_model(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT COALESCE(NULLIF(model, ''), 'unknown') AS model,
               COUNT(*) AS runs,
               COALESCE(SUM(input_tokens + output_tokens), 0) AS tokens,
               COALESCE(SUM(COALESCE(actual_cost_usd, estimated_cost_usd)), 0) AS cost_usd
        FROM sessions
        WHERE source != 'cron'
        GROUP BY model ORDER BY tokens DESC LIMIT 10
        """
    ).fetchall()
    return [dict(r) for r in rows]
