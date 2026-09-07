"""RunBridge — forwards chat requests to the gateway and streams typed events.

The Android runtime exposes a local gateway (chat-completions SSE at
``POST /v1/chat/completions``). ``RunBridge.run_chat``:

1. Registers a run on the RunManager.
2. POSTs the (bridge-stamped) request to the gateway chat-completions endpoint.
3. Reads the gateway SSE stream, translating each item into typed hermes
   frames via ``RunEventEmitter``, and reconciles RunState (approval, steer).
4. On stop, interrupts the gateway agent and marks the run stopped.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Optional

from hermes_android.runs.manager import (
    ApprovalRequest,
    ClarifyRequest,
    RunManager,
    RunState,
    RunStatus,
    get_run_manager,
)


@dataclass
class GatewayClient:
    """Minimal blocking HTTP SSE client for the local gateway.

    Uses stdlib ``http.client`` so it runs inside Chaquopy without OkHttp.
    """

    base_url: str
    api_key: str = ""

    def open_chat_stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        stream: bool = True,
        session_id: Optional[str] = None,
        bridge_version: int = 1,
        ephemeral_system_prompt: Optional[str] = None,
    ) -> Any:
        """Open a chat-completions SSE connection. Returns an iterable of raw
        (lines) wrapped so the caller can .close()."""
        import http.client
        import urllib.parse

        url = f"{self.base_url}/v1/chat/completions"
        if self.base_url.endswith("/"):
            url = f"{self.base_url}v1/chat/completions"

        body: dict[str, Any] = {
            "model": model,
            "stream": stream,
            "messages": messages,
            "bridge_version": bridge_version,
        }
        if ephemeral_system_prompt:
            body["ephemeral_system_prompt"] = ephemeral_system_prompt

        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if session_id:
            headers["X-Hermes-Session-Id"] = session_id

        parsed = urllib.parse.urlsplit(self.base_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 8080
        conn = http.client.HTTPConnection(host, port, timeout=180)
        conn.request(
            "POST",
            "/v1/chat/completions",
            body=json.dumps(body),
            headers=headers,
        )
        resp = conn.getresponse()
        return _GatewayStream(resp, conn)


class _GatewayStream:
    """Wraps an httplib response that yields raw SSE lines and can close."""

    def __init__(self, resp, conn):
        self._resp = resp
        self._conn = conn

    @property
    def status(self) -> int:
        return self._resp.status

    @property
    def reason(self) -> str:
        return self._resp.reason

    def lines(self) -> Any:
        return self._resp

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass


_STOP_MARKER = object()


class RunBridge:
    """Owns the chat <-> gateway forwarding for one session."""

    def __init__(
        self,
        gateway_client: GatewayClient,
        *,
        run_manager: Optional[RunManager] = None,
    ):
        self._gateway = gateway_client
        self._manager = run_manager or get_run_manager()
        self._stop_flags: dict[str, threading.Event] = {}

    # --- Steer / approval / clarify / stop (called by HTTP routes) ---

    def steer(self, run_id: str, message: str) -> dict[str, Any]:
        run = self._manager.require(run_id, "RUN_NOT_FOUND")
        msg = run.enqueue_steer(message)
        return {
            "success": True,
            "run_id": run_id,
            "queued": True,
            "queued_at_ms": msg.queued_at_ms,
        }

    def approve(self, run_id: str, approval_id: str, approved: bool,
                allow_always: bool = False) -> dict[str, Any]:
        run = self._manager.require(run_id, "RUN_NOT_FOUND")
        pending = run.pending_approval()
        if pending is None or pending.approval_id != approval_id:
            return {
                "success": False,
                "run_id": run_id,
                "error": "No matching pending approval",
                "code": "NO_PENDING_APPROVAL",
            }
        run.clear_approval()
        # In a real gateway integration the approval verdict is delivered to the
        # blocked tool via an event.queue. Here we store it so the blocking
        # stream loop can observe it via run.stream_verdicts.
        run.service_verdict = {
            "kind": "approval",
            "approval_id": approval_id,
            "approved": approved,
            "allow_always": allow_always,
            "ts": int(time.time() * 1000),
        }
        return {"success": True, "run_id": run_id, "approved": approved}

    def clarify(self, run_id: str, response: str) -> dict[str, Any]:
        run = self._manager.require(run_id, "RUN_NOT_FOUND")
        pending = run.pending_clarify()
        if pending is None:
            return {
                "success": False,
                "run_id": run_id,
                "error": "No pending clarify prompt",
                "code": "NO_PENDING_CLARIFY",
            }
        run.clear_clarify()
        run.service_verdict = {
            "kind": "clarify",
            "response": response,
            "ts": int(time.time() * 1000),
        }
        return {"success": True, "run_id": run_id}

    def stop(self, run_id: str) -> dict[str, Any]:
        run = self._manager.require(run_id, "RUN_NOT_FOUND")
        ok = run.request_stop()
        # Wake any blocking stream loop (if registered) so it can interrupt the agent.
        evt = self._stop_flags.get(run_id)
        if evt is not None:
            evt.set()
        return {"success": True, "run_id": run_id, "stop_requested": ok}

    def status(self, run_id: str) -> dict[str, Any]:
        run = self._manager.require(run_id, "RUN_NOT_FOUND")
        return run.snapshot()


def _register_stop_flag(bridge: RunBridge, run_id: str) -> threading.Event:
    evt = threading.Event()
    bridge._stop_flags[run_id] = evt
    return evt


def _unregister_stop_flag(bridge: RunBridge, run_id: str) -> None:
    bridge._stop_flags.pop(run_id, None)


def _read_sse_lines(stream: _GatewayStream) -> Any:
    """Yield decoded SSE data payloads/lines from the gateway stream.

    The gateway emits chat-completions SSE: each event is one or more
    ``data: <json>`` lines separated by a blank line, plus the custom
    ``event: hermes.tool.progress`` frame. We group by data payload per event
    to reconstruct the :class:`~._GatewayItem` stream.
    """
    resp = stream.lines()
    event_name = None
    current_payloads: list[str] = []

    def flush():
        if not current_payloads:
            return
        text = "\n".join(current_payloads)
        current_payloads.clear()
        if text == "[DONE]":
            text = None
        return (event_name, text)

    for raw_line in resp:
        line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
        if line == "":
            item = flush()
            if item is not None:
                yield item
            event_name = None
            continue
        if line.startswith(":"):
            # SSE comment / keepalive
            continue
        if line.startswith("event:"):
            event_name = line[len("event:"):].strip()
            continue
        if line.startswith("data:"):
            payload = line[len("data:"):].strip()
            if payload:
                current_payloads.append(payload)
            continue
        # Other lines ignored
    item = flush()
    if item is not None:
        yield item


def iter_gateway_items(stream: _GatewayStream) -> Any:
    """Convert raw SSE lines into :class:`~._GatewayItem` objects.

    Returns an iterator of:
        - str  : content delta
        - ("__tool_progress__", dict) : tool lifecycle
        - dict : raw typed passthrough (shouldn't normally happen from gateway)
        - None : sentinel (DONE)
    Raises on non-200.
    """
    if stream.status != 200:
        raise ConnectionError(
            f"gateway returned HTTP {stream.status} {stream.reason}"
        )

    for _event_name, payload in _read_sse_lines(stream):
        if payload is None:
            yield None
            continue
        data = json.loads(payload)
        # Custom tool progress event frame was re-emitted as event-name'd line.
        if isinstance(data, dict):
            # Tool progress payloads carry toolCallId + status; content chunks carry "choices".
            if "toolCallId" in data or ("status" in data and "tool" in data):
                yield ("__tool_progress__", data)
                continue
            if "choices" in data and data.get("choices"):
                choice = data["choices"][0]
                delta = (choice.get("delta") or {}).get("content") or (choice.get("message") or {}).get("content") or ""
                if delta:
                    yield delta
                continue
            if "error" in data:
                yield data
                continue
            # Unknown wrapper — default to delta of any string fields
            fallback = (data.get("content") or data.get("delta") or "")
            if fallback:
                yield fallback
            else:
                yield data
        else:
            yield data


def _make_gateway_messages(
    messages: list[dict[str, Any]],
    ephemeral_system_prompt: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Normalize client chat messages for the gateway.

    Accepts OpenAI-style messages and the Android bridge ChatMessage shape
    (role/content, plus images -> multimodal parts).
    """
    out: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        images = msg.get("images") or []
        if images:
            parts: list[dict[str, Any]] = []
            if content:
                parts.append({"type": "text", "text": content})
            for img in images:
                parts.append({
                    "type": "image_url",
                    "image_url": {"url": img if img.startswith(("data:", "http")) else f"data:image/png;base64,{img}"},
                })
            out.append({"role": role, "content": parts})
        else:
            out.append({"role": role, "content": content})
    if ephemeral_system_prompt:
        out.insert(0, {"role": "system", "content": ephemeral_system_prompt})
    return out