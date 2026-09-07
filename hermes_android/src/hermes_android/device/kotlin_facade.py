"""Kotlin-backed DeviceFacade implementation (P2).

Implements the typed Python ``DeviceFacade`` protocol by dispatching every
call over Chaquopy to a single static Kotlin entry point
(``HermesDeviceFacadeBridge.dispatchJson``). This is how the agent's executor
threads reach Kotlin capability implementations without one bridge class per
operation: one wire contract, one dispatcher.

Envelope contract (matches HermesDeviceFacadeBridge.kt):

    request  : {"op": "<snake_case>", "args": {...}}
    response : {"success": true, "data": <jsonable>}
             | {"success": false, "error_code": "...", "error_message": "..."}
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from hermes_android.device.facade import DeviceFacade, FacadeResult
from hermes_android.device.registry import register_facade

logger = logging.getLogger(__name__)

_BRIDGE_CLASS = "com.mobilefork.hermesagent.device.HermesDeviceFacadeBridge"


def _bridge_class():
    from java import jclass  # type: ignore # noqa: PLC0415 - Chaquopy only

    return jclass(_BRIDGE_CLASS)


def kotlin_facade_available() -> bool:
    """True only when running under Chaquopy with the Kotlin bridge loaded."""
    try:
        _bridge_class()
        return True
    except Exception:
        return False


class KotlinDispatchFacade(DeviceFacade):
    """Typed facade backed by the single Kotlin JSON dispatcher."""

    def _call(self, operation: str, **args: Any) -> FacadeResult:
        try:
            bridge = _bridge_class()
            raw = bridge.dispatchJson(operation, json.dumps({"op": operation, "args": args}))
            payload = json.loads(raw)
        except Exception as exc:  # noqa: BLE001 - transport failures are typed
            return FacadeResult.err("DEVICE_UNAVAILABLE", f"{operation} failed: {exc}")
        if not isinstance(payload, dict):
            return FacadeResult.err("DEVICE_UNAVAILABLE", f"{operation}: malformed bridge response")
        if not payload.get("success"):
            return FacadeResult.err(
                str(payload.get("error_code") or "DEVICE_UNAVAILABLE"),
                str(payload.get("error_message") or f"{operation} failed"),
            )
        return FacadeResult.ok(payload.get("data"))

    # --- Terminal / Process ---

    def terminal_exec(self, command: str, timeout_seconds: int = 30,
                      run_id: Optional[str] = None) -> FacadeResult:
        return self._call("terminal_exec", command=command, timeout_seconds=timeout_seconds, run_id=run_id)

    def terminal_spawn(self, command: str, cwd: Optional[str] = None,
                       env: Optional[dict[str, str]] = None,
                       run_id: Optional[str] = None) -> FacadeResult:
        return self._call("terminal_spawn", command=command, cwd=cwd, env=env, run_id=run_id)

    def terminal_kill(self, pid: int, run_id: Optional[str] = None) -> FacadeResult:
        return self._call("terminal_kill", pid=pid, run_id=run_id)

    def terminal_list(self, run_id: Optional[str] = None) -> FacadeResult:
        return self._call("terminal_list", run_id=run_id)

    # --- File I/O ---

    def file_read(self, path: str, max_chars: int = 100_000,
                  run_id: Optional[str] = None) -> FacadeResult:
        return self._call("file_read", path=path, max_chars=max_chars, run_id=run_id)

    def file_write(self, path: str, content: str, append: bool = False,
                   run_id: Optional[str] = None) -> FacadeResult:
        return self._call("file_write", path=path, content=content, append=append, run_id=run_id)

    def file_list(self, path: str, recursive: bool = False,
                  run_id: Optional[str] = None) -> FacadeResult:
        return self._call("file_list", path=path, recursive=recursive, run_id=run_id)

    def file_delete(self, path: str, run_id: Optional[str] = None) -> FacadeResult:
        return self._call("file_delete", path=path, run_id=run_id)

    def file_search(self, path: str, pattern: str,
                    run_id: Optional[str] = None) -> FacadeResult:
        return self._call("file_search", path=path, pattern=pattern, run_id=run_id)

    # --- System ---

    def system_info(self, run_id: Optional[str] = None) -> FacadeResult:
        return self._call("system_info", run_id=run_id)

    def system_action(self, action: str, args: Optional[dict[str, Any]] = None,
                      run_id: Optional[str] = None) -> FacadeResult:
        return self._call("system_action", action=action, args=args, run_id=run_id)

    # --- Accessibility ---

    def accessibility_snapshot(self, limit: int = 80,
                               run_id: Optional[str] = None) -> FacadeResult:
        return self._call("accessibility_snapshot", limit=limit, run_id=run_id)

    def accessibility_action(self, action: str, **kwargs: Any) -> FacadeResult:
        return self._call("accessibility_action", action=action, **kwargs)

    # --- Projection / Screen ---

    def projection_start(self, run_id: Optional[str] = None) -> FacadeResult:
        return self._call("projection_start", run_id=run_id)

    def projection_stop(self, run_id: Optional[str] = None) -> FacadeResult:
        return self._call("projection_stop", run_id=run_id)

    def projection_screenshot(self, run_id: Optional[str] = None) -> FacadeResult:
        return self._call("projection_screenshot", run_id=run_id)

    # --- Sensors / Location ---

    def sensors_list(self, run_id: Optional[str] = None) -> FacadeResult:
        return self._call("sensors_list", run_id=run_id)

    def sensors_read(self, sensor_type: str, run_id: Optional[str] = None) -> FacadeResult:
        return self._call("sensors_read", sensor_type=sensor_type, run_id=run_id)

    def location_get(self, run_id: Optional[str] = None) -> FacadeResult:
        return self._call("location_get", run_id=run_id)

    # --- Calendar / Logcat / Notifications ---

    def calendar_query(self, query: str, run_id: Optional[str] = None) -> FacadeResult:
        return self._call("calendar_query", query=query, run_id=run_id)

    def logcat_read(self, filter_spec: str = "", max_lines: int = 100,
                    run_id: Optional[str] = None) -> FacadeResult:
        return self._call("logcat_read", filter_spec=filter_spec, max_lines=max_lines, run_id=run_id)

    def notifications_list(self, limit: int = 50,
                           run_id: Optional[str] = None) -> FacadeResult:
        return self._call("notifications_list", limit=limit, run_id=run_id)

    # --- Clipboard / Share ---

    def clipboard_get(self, run_id: Optional[str] = None) -> FacadeResult:
        return self._call("clipboard_get", run_id=run_id)

    def clipboard_set(self, content: str, run_id: Optional[str] = None) -> FacadeResult:
        return self._call("clipboard_set", content=content, run_id=run_id)

    def share_send(self, content: str, mime_type: str = "text/plain",
                   run_id: Optional[str] = None) -> FacadeResult:
        return self._call("share_send", content=content, mime_type=mime_type, run_id=run_id)

    # --- TTS / STT ---

    def tts_speak(self, text: str, language: Optional[str] = None,
                  run_id: Optional[str] = None) -> FacadeResult:
        return self._call("tts_speak", text=text, language=language, run_id=run_id)

    def stt_listen(self, language: Optional[str] = None, timeout_seconds: int = 30,
                   run_id: Optional[str] = None) -> FacadeResult:
        return self._call("stt_listen", language=language, timeout_seconds=timeout_seconds, run_id=run_id)

    def notification_post(self, title: str, body: str, channel: str = "hermes",
                          run_id: Optional[str] = None) -> FacadeResult:
        return self._call("notification_post", title=title, body=body, channel=channel, run_id=run_id)

    # --- Apps ---

    def apps_list(self, run_id: Optional[str] = None) -> FacadeResult:
        return self._call("apps_list", run_id=run_id)

    def apps_launch(self, package_name: str, run_id: Optional[str] = None) -> FacadeResult:
        return self._call("apps_launch", package_name=package_name, run_id=run_id)

    # --- Resources / Cleanup ---

    def resources_get(self, run_id: Optional[str] = None) -> FacadeResult:
        return self._call("resources_get", run_id=run_id)

    def cleanup_run(self, components: Optional[list[str]] = None,
                    run_id: Optional[str] = None) -> FacadeResult:
        return self._call("cleanup_run", components=components, run_id=run_id)


def try_register_kotlin_facade() -> bool:
    """Register the Kotlin-backed facade when running under Chaquopy.

    Non-fatal by design: on desktop/test interpreters there is no `java`
    module and the registry keeps its stub.
    """
    if not kotlin_facade_available():
        logger.info("[device_facade] Kotlin bridge unavailable; keeping stub facade")
        return False
    register_facade(KotlinDispatchFacade())
    logger.info("[device_facade] Kotlin-backed device facade registered")
    return True
