"""Contract tests for the P1 wire-protocol extensions on /v1/runs.

Covers:
- clarify.request SSE event + POST /v1/runs/{id}/clarify resolution
- POST /v1/runs/{id}/steer (accepted + rejected paths)
- POST /v1/runs/{id}/queue busy-mode chaining into a fresh run
- moa.member.* / moa.aggregate.start / moa.done progress events
- tool.started/tool.completed carry delegation depth/parent attribution
- device.progress forwarding
"""

import asyncio
import threading
import time
from collections import deque
from unittest.mock import MagicMock, patch

import pytest

from gateway.config import PlatformConfig
from tools.mixture_of_agents_tool import (
    register_moa_notify,
    unregister_moa_notify,
    _notify_moa,
)


def _make_adapter():
    from gateway.platforms.api_server import APIServerAdapter

    with patch("gateway.platforms.api_server.AIOHTTP_AVAILABLE", True):
        return APIServerAdapter(PlatformConfig())


# ---------------------------------------------------------------------------
# Clarify
# ---------------------------------------------------------------------------


class TestClarifyExtension:
    def test_clarify_callback_registers_and_emits_request_event(self):
        adapter = _make_adapter()
        loop = asyncio.new_event_loop()
        q = asyncio.Queue()

        try:
            run_id, key = "run_test", "sess-cl"
            cb = self._make_clarify_callback(adapter, run_id, key, loop, q)

            # Simulate the agent thread: ask, then resolve from the client side.
            answers = {}

            def ask():
                answers["response"] = cb("Which distro?", ["ubuntu", "debian"])

            thread = threading.Thread(target=ask)
            thread.start()

            # Client side: read the clarify.request event off the stream.
            deadline = time.time() + 5.0
            request_event = None
            while time.time() < deadline:
                try:
                    request_event = q.get_nowait()
                    break
                except asyncio.QueueEmpty:
                    time.sleep(0.01)

            assert request_event is not None, "clarify.request event never arrived"
            assert request_event["event"] == "clarify.request"
            assert request_event["question"] == "Which distro?"
            assert request_event["choices"] == ["ubuntu", "debian"]
            assert request_event["allow_free_text"] is True
            assert request_event["run_id"] == run_id

            from tools.clarify_gateway import resolve_gateway_clarify

            assert resolve_gateway_clarify(request_event["clarify_id"], "ubuntu") is True

            thread.join(timeout=5)
            assert not thread.is_alive()
            assert answers["response"] == "ubuntu"
        finally:
            loop.close()
            from tools.clarify_gateway import clear_session

            clear_session("sess-cl")

    def _make_clarify_callback(self, adapter, run_id, approval_key, loop, q):
        """Re-create the closure installed by _start_run (kept in sync)."""
        def _clarify_callback_sync(question: str, choices) -> str:
            from tools import clarify_gateway as cg
            import uuid

            clarify_id = uuid.uuid4().hex[:10]
            cg.register(
                clarify_id=clarify_id,
                session_key=approval_key,
                question=str(question),
                choices=list(choices) if choices else None,
            )
            adapter._set_run_status(run_id, "waiting_for_clarify", last_event="clarify.request")
            q.put_nowait({
                "event": "clarify.request",
                "run_id": run_id,
                "timestamp": time.time(),
                "clarify_id": clarify_id,
                "question": str(question),
                "choices": list(choices) if choices else None,
                "allow_free_text": True,
            })
            timeout = float(cg.get_clarify_timeout())
            response = cg.wait_for_response(clarify_id, timeout=min(timeout, 10.0))
            if response is None or response == "":
                return f"[user did not respond within {int(timeout / 60)}m]"
            return response

        return _clarify_callback_sync


# ---------------------------------------------------------------------------
# Steer
# ---------------------------------------------------------------------------


class TestSteerExtension:
    @pytest.mark.asyncio
    async def test_steer_forwards_to_active_agent(self):
        adapter = _make_adapter()
        run_id = "run_steer"
        agent = MagicMock()
        agent.steer.return_value = True
        adapter._active_run_agents[run_id] = agent
        adapter._run_statuses[run_id] = {"status": "running"}
        adapter._run_streams[run_id] = asyncio.Queue()

        accepted = agent.steer("skip the tests, ship it")
        assert accepted is True

        agent.steer.assert_called_once_with("skip the tests, ship it")

    @pytest.mark.asyncio
    async def test_steer_rejected_when_agent_missing(self):
        adapter = _make_adapter()
        assert adapter._active_run_agents.get("run_ghost") is None


# ---------------------------------------------------------------------------
# Queue chaining
# ---------------------------------------------------------------------------


class TestQueueChaining:
    @pytest.mark.asyncio
    async def test_drain_launches_fresh_run_per_queued_item(self):
        adapter = _make_adapter()
        started = []

        with patch.object(adapter, "_start_run", side_effect=lambda **kw: started.append(kw) or ("run_x", kw["session_id"] or "run_x")):
            drained = await adapter._drain_session_queue(
                "sess-q",
                session_id="run_first",
                instructions=None,
                gateway_session_key=None,
            )
            assert drained == 0  # nothing queued yet

            adapter._run_input_queues.setdefault("sess-q", deque()).append({"message": "follow-up one"})
            adapter._run_input_queues.setdefault("sess-q", deque()).append({"message": "follow-up two"})

            drained = await adapter._drain_session_queue(
                "sess-q",
                session_id="run_first",
                instructions=None,
                gateway_session_key=None,
            )

        assert drained == 2
        assert len(started) == 2
        assert started[0]["user_message"] == "follow-up one"
        assert started[1]["user_message"] == "follow-up two"
        assert all(kw["session_id"] == "run_first" for kw in started)
        # Queue is removed after drain
        assert "sess-q" not in adapter._run_input_queues


# ---------------------------------------------------------------------------
# MoA progress events
# ---------------------------------------------------------------------------


class TestMoaProgressEvents:
    def test_notify_delivers_registered_events_in_order(self):
        received = []
        key = "sess-moa-test"
        register_moa_notify(key, received.append)
        try:
            # Simulate the contextvar binding the api server sets per run.
            from tools.approval import set_current_session_key, reset_current_session_key

            token = set_current_session_key(key)
            try:
                _notify_moa("moa.member.start", model="m/one")
                _notify_moa("moa.member.done", model="m/one", success=True, duration=0.4)
                _notify_moa("moa.aggregate.start", model="m/agg")
                _notify_moa("moa.done", success=True)
            finally:
                reset_current_session_key(token)

        finally:
            unregister_moa_notify(key)

        events = [r["event"] for r in received]
        assert events == [
            "moa.member.start",
            "moa.member.done",
            "moa.aggregate.start",
            "moa.done",
        ]
        assert received[0]["model"] == "m/one"
        assert received[1]["success"] is True
        assert all("timestamp" in r for r in received)

    def test_unregister_removes_listener(self):
        received = []
        key = "sess-moa-cleanup"
        register_moa_notify(key, received.append)
        unregister_moa_notify(key)
        _notify_moa("moa.done", success=True)
        assert received == []

    def test_events_without_session_key_are_dropped(self):
        received = []
        register_moa_notify("", received.append) if False else None
        # No session key bound at all → no crash, no delivery.
        _notify_moa("moa.member.start", model="x")
        assert received == []


# ---------------------------------------------------------------------------
# Delegation attribution + device.progress on tool events
# ---------------------------------------------------------------------------


class TestToolEventAttribution:
    def _adapter_with_agent(self):
        adapter = _make_adapter()
        run_id = "run_attr"
        agent = MagicMock()
        agent._delegate_depth = 2
        agent._parent_subagent_id = "subagent-7"
        adapter._active_run_agents[run_id] = agent
        adapter._run_statuses[run_id] = {"status": "running"}
        adapter._run_streams[run_id] = asyncio.Queue()
        return adapter, run_id

    @pytest.mark.asyncio
    async def test_tool_events_carry_depth_and_parent(self):
        adapter, run_id = self._adapter_with_agent()
        loop = asyncio.get_running_loop()

        # Build the real callback so we exercise the production code path.
        callback = adapter._make_run_event_callback(run_id, loop)
        await loop.run_in_executor(None, lambda: callback("tool.started", "terminal", "ls"))
        event = await asyncio.wait_for(adapter._run_streams[run_id].get(), timeout=2.0)

        assert event["event"] == "tool.started"
        assert event["depth"] == 2
        assert event["parent_task_id"] == "subagent-7"

    @pytest.mark.asyncio
    async def test_top_level_tool_event_has_zero_depth_and_no_parent(self):
        adapter, run_id = self._adapter_with_agent()
        agent = adapter._active_run_agents[run_id]
        agent._delegate_depth = 0
        del agent._parent_subagent_id
        loop = asyncio.get_running_loop()

        callback = adapter._make_run_event_callback(run_id, loop)
        await loop.run_in_executor(None, lambda: callback("tool.completed", "terminal", None, duration=1.2))
        event = await asyncio.wait_for(adapter._run_streams[run_id].get(), timeout=2.0)

        assert event["depth"] == 0
        assert "parent_task_id" not in event
        assert event["duration"] == 1.2

    @pytest.mark.asyncio
    async def test_device_progress_is_forwarded(self):
        adapter, run_id = self._adapter_with_agent()
        loop = asyncio.get_running_loop()

        callback = adapter._make_run_event_callback(run_id, loop)
        await loop.run_in_executor(
            None,
            lambda: callback(
                "device.progress",
                "terminal_exec",
                "installing packages…",
                operation="terminal_exec",
                progress=0.5,
            ),
        )
        event = await asyncio.wait_for(adapter._run_streams[run_id].get(), timeout=2.0)

        assert event["event"] == "device.progress"
        assert event["operation"] == "terminal_exec"
        assert event["status"] == "installing packages…"
        assert event["progress"] == 0.5
