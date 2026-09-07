"""RunEventEmitter — produces typed hermes SSE frames.

Consumes a sequence of items from the underlying gateway chat-completions SSE
(plain string deltas, ``("__tool_progress__", payload)`` tuples, etc.) and
re-emits them as typed hermes events on the wire. It also interleaves
Android-specific events (clarify, MoA, delegate, device progress, steer,
transient lifecycle) that the gateway does not naturally emit.

Wire format on the SSE/SSE response is a single SSE stream of frames::

    event: message_delta
    data: {"run_id": "...", "timestamp": ..., "delta": "..."}
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Callable, Iterable, Optional

from hermes_android.api.events import (
    SSEEventType,
    create_clarify_request,
    create_device_progress,
    create_moa_aggregate_start,
    create_moa_member_delta,
    create_moa_member_done,
    create_moa_member_start,
    create_delegate_start,
    create_delegate_done,
)
from hermes_android.runs.manager import RunState, RunStatus


class EmitterStopped(Exception):
    """Raised when the emitter is asked to stop mid-stream."""


def sse_frame(event_name: str, data: dict[str, Any], run_id: str) -> str:
    """Format a single SSE frame with the doc headers the Kotlin decoder expects."""
    payload = dict(data)
    payload.setdefault("run_id", run_id)
    payload.setdefault("timestamp", int(time.time() * 1000))
    return (
        f"event: {event_name}\n"
        f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"
    )


class RunEventEmitter:
    """Translates gateway stream items into typed hermes SSE frames.

    The emitter is a callable that yields SSE frame strings. It tracks a
    RunState and reconciles transient changes into typed events.
    """

    def __init__(
        self,
        run: RunState,
        *,
        should_stop: Callable[[], bool] = lambda: False,
    ):
        self._run = run
        self._should_stop = should_stop
        self._seen_tools: set[str] = set()

    # --- Core translation: yield typed frames for gateway items ---

    def translate(
        self,
        items: Iterable[Any],
    ) -> Iterable[str]:
        """Yield typed SSE frames for the gateway stream items.

        Items are either:
            - plain str            -> message_delta
            - ("__tool_progress__", dict) -> tool.progress running/completed
            - None                 -> sentinel -> raise EmitterStopped
            - dict                 -> raw typed event passthrough (run_id stamped)
        """
        for item in items:
            if self._should_stop():
                raise EmitterStopped()

            if isinstance(item, str):
                yield self._delta(item)
            elif isinstance(item, tuple) and len(item) == 2 and item[0] == "__tool_progress__":
                yield self._tool_progress(item[1])
            elif isinstance(item, dict):
                yield self._passthrough(item)
            elif item is None:
                raise EmitterStopped()

    # --- Typed frame builders ---

    def _delta(self, chunk: str) -> str:
        return sse_frame(
            SSEEventType.MESSAGE_DELTA.value,
            {"delta": chunk},
            self._run.run_id,
        )

    def _tool_progress(self, payload: dict[str, Any]) -> str:
        tool_call_id = payload.get("toolCallId") or payload.get("tool_call_id") or ""
        status = payload.get("status", "running")
        if status == "completed":
            self._seen_tools.discard(tool_call_id)
            self._run.clear_tool()
            return sse_frame(
                SSEEventType.TOOL_PROGRESS.value,
                {
                    "tool": payload.get("tool", ""),
                    "toolCallId": tool_call_id,
                    "status": "completed",
                },
                self._run.run_id,
            )
        # running
        if tool_call_id:
            self._seen_tools.add(tool_call_id)
            self._run.set_tool_running(tool_call_id, payload.get("tool", ""))
        return sse_frame(
            SSEEventType.TOOL_PROGRESS.value,
            {
                "tool": payload.get("tool", ""),
                "emoji": payload.get("emoji"),
                "label": payload.get("label"),
                "toolCallId": tool_call_id,
                "status": "running",
            },
            self._run.run_id,
        )

    def _passthrough(self, raw: dict[str, Any]) -> str:
        event_name = raw.get("event") or raw.get("type")
        if not event_name:
            # Default to message delta content if we only have a string payload
            content = raw.get("content")
            if content:
                return self._delta(str(content))
            return self._delta(json.dumps(raw, separators=(',', ':')))
        data = {k: v for k, v in raw.items() if k not in ("event", "type", "run_id", "timestamp")}
        return sse_frame(event_name, data, self._run.run_id)

    # --- Android-specific event emitters (used by the run endpoint) ---

    def clarify(self, prompt: str, choices: Optional[list[str]] = None,
                allow_free_text: bool = True, timeout_seconds: int = 120) -> str:
        event = create_clarify_request(
            self._run.run_id, prompt, choices, allow_free_text, timeout_seconds
        )
        from hermes_android.api.events import SSEEvent
        payload = dict(event.data)
        return sse_frame(event.event, payload, self._run.run_id)

    def device_progress(self, tool_call_id: str, operation: str,
                        progress: float, message: str = "") -> str:
        event = create_device_progress(
            self._run.run_id, tool_call_id, operation, progress, message
        )
        return sse_frame(event.event, dict(event.data), self._run.run_id)