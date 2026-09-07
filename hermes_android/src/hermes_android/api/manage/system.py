"""System management routes — resources, cleanup, logs.

Resource gauges never fabricate numbers: per-process RAM/threads come from
/proc (always present on Android); CPU percent is reported only when psutil
is available; GPU/NPU are null unless a backend self-reports (none do here).
"""

from __future__ import annotations

import gc
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from aiohttp import web

from hermes_android.api.manage import BRIDGE_VERSION, hermes_home_dir, json_response

logger = logging.getLogger(__name__)


def json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload)


def register_routes(web_app: web.Application) -> None:
    async def resources(request: web.Request) -> web.Response:
        return json_response(_collect_resources())

    async def cleanup(request: web.Request) -> web.Response:
        return json_response(await _run_cleanup(request))

    async def logs(request: web.Request) -> web.Response:
        level = request.query.get("level", "INFO").upper()
        source = request.query.get("source", "agent")
        tail = max(1, min(int(request.query.get("tail", "200")), 2000))
        return json_response(_read_logs(source=source, level=level, tail=tail))

    web_app.router.add_get("/v1/manage/system/resources", resources)
    web_app.router.add_post("/v1/manage/system/cleanup", cleanup)
    web_app.router.add_get("/v1/manage/system/logs", logs)


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


def _rss_kb() -> int:
    try:
        status = Path("/proc/self/status")
        for line in status.read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except Exception:
        pass
    return 0


def _thread_count() -> int:
    try:
        return len(Path("/proc/self/task").iterdir())
    except Exception:
        try:
            return int(os.environ.get("_", "0")) and 0 or 0
        except Exception:
            return 0


def _cpu_percent() -> float | None:
    try:
        import psutil  # type: ignore

        return float(psutil.Process(os.getpid()).cpu_percent(interval=None))
    except Exception:
        return None  # stock Android exposes no per-app CPU without psutil


def _collect_resources() -> dict[str, Any]:
    rss_mb = round(_rss_kb() / 1024.0, 1)
    return {
        "python": {
            "pid": os.getpid(),
            "rss_mb": rss_mb,
            "threads": _thread_count(),
            "cpu_percent": _cpu_percent(),
        },
        # Kotlin-side numbers are filled by the app from its own process stats.
        "app": None,
        "local_model": None,
        "linux": _linux_rss_mb(),
        "gpu_percent": None,
        "npu_percent": None,
        "note": "GPU/NPU appear only when a backend self-reports; stock Android hides them.",
    }


def _linux_rss_mb() -> float | None:
    """RSS of the Linux subsystem shell, when its state file names one."""
    try:
        files_dir = Path(os.environ.get("HERMES_ANDROID_FILES_DIR", "") or "")
        if not files_dir.is_dir():
            return None
        state_path = files_dir / "hermes-home" / "linux" / "linux-subsystem-state.json"
        if not state_path.is_file():
            return None
        import json as _json

        state = _json.loads(state_path.read_text(encoding="utf-8"))
        bash_path = state.get("shell_path") or state.get("bash_path") or ""
        if not bash_path:
            return None
        # Find processes whose exe resolves into the subsystem prefix.
        total_kb = 0
        prefix = str(Path(bash_path).parent.parent)
        for proc in Path("/proc").iterdir():
            if not proc.name.isdigit():
                continue
            try:
                exe = proc / "exe"
                target = exe.resolve()
                if str(target).startswith(prefix):
                    for line in (proc / "status").read_text(encoding="utf-8").splitlines():
                        if line.startswith("VmRSS:"):
                            total_kb += int(line.split()[1])
                            break
            except Exception:
                continue
        return round(total_kb / 1024.0, 1) if total_kb else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Cleanup — never aborts a running agent
# ---------------------------------------------------------------------------


async def _run_cleanup(request: web.Request) -> dict[str, Any]:
    freed_before = _rss_kb()
    per_component: dict[str, Any] = {}
    skipped: list[str] = []

    # Python GC
    collected = gc.collect()
    per_component["python_gc"] = {"objects_collected": collected}

    # Drop idle auxiliary clients (best-effort; module may be absent)
    try:
        from agent.auxiliary_client import drop_idle_clients

        dropped = drop_idle_clients()
        per_component["aux_clients"] = {"dropped": dropped}
    except ImportError:
        skipped.append("aux_clients")
    except Exception as exc:
        skipped.append(f"aux_clients:{exc}")

    # Trim stored responses in the shared api server app (tool-result storage)
    adapter = request.app.get("api_server_adapter")
    store = getattr(adapter, "_response_store", None) if adapter is not None else None
    if store is not None and hasattr(store, "trim"):
        try:
            per_component["response_store"] = {"trimmed": store.trim()}
        except Exception as exc:
            skipped.append(f"response_store:{exc}")
    else:
        skipped.append("response_store")

    time.sleep(0.05)
    freed_after = _rss_kb()
    freed_mb = max(0.0, round((freed_before - freed_after) / 1024.0, 1))
    return {"freed_mb": freed_mb, "per_component": per_component, "skipped": skipped}


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------

_LOG_SOURCES = ("agent", "errors", "gateway")


def _read_logs(*, source: str, level: str, tail: int) -> dict[str, Any]:
    if source not in _LOG_SOURCES:
        raise web.HTTPBadRequest(
            text=json_dumps({
                "error": f"Unknown log source '{source}'; expected one of {_LOG_SOURCES}",
                "code": "INVALID_ARGUMENT",
                "bridge_version": BRIDGE_VERSION,
            }),
            content_type="application/json",
        )
    log_path = hermes_home_dir() / "logs" / f"{source}.log"
    if not log_path.is_file():
        return {"lines": [], "source": source, "level": level}
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    if level in {"WARNING", "ERROR"} and source != "errors":
        threshold = {"INFO": 10, "WARNING": 20, "ERROR": 30}.get(level, 10)
        kept = []
        for line in lines:
            match_level = 10
            if " ERROR " in line or " - ERROR - " in line:
                match_level = 30
            elif " WARNING " in line or " - WARNING - " in line:
                match_level = 20
            if match_level >= threshold:
                kept.append(line)
        lines = kept
    return {"lines": lines[-tail:], "source": source, "level": level}
