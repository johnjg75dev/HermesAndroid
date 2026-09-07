"""RunManager — tracks active Hermes runs and their transient lifecycle.

A *run* is one agent loop started via ``POST /v1/runs/{id}/chat``. The manager
owns the run's mutable, transient state — steer queue, pending approvals,
pending clarify, stop flag — while the prompt-cache baseline payload stays
untouched on the Kotlin side.

Run states mirror ``HermesRunState`` in Kotlin:
    thinking / tool_running / awaiting_approval / awaiting_clarify /
    moa_member_running / moa_aggregating / delegate_running /
    finished / failed / stopped
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class RunStatus(Enum):
    """Transient run status (matches Kotlin HermesRunState)."""

    THINKING = "thinking"
    TOOL_RUNNING = "tool_running"
    AWAITING_APPROVAL = "awaiting_approval"
    AWAITING_CLARIFY = "awaiting_clarify"
    MOA_MEMBER_RUNNING = "moa_member_running"
    MOA_AGGREGATING = "moa_aggregating"
    DELEGATE_RUNNING = "delegate_running"
    FINISHED = "finished"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass
class SteerMessage:
    """A user message queued mid-run; consumed at the next safe break point."""

    text: str
    queued_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))


@dataclass
class ApprovalRequest:
    """Pending approval prompt that blocks tools until answered."""

    approval_id: str
    tool: str
    action: str
    description: str
    risk_level: Optional[str] = None
    allow_always: bool = True


@dataclass
class ClarifyRequest:
    """Pending clarify prompt that blocks the run until answered."""

    prompt: str
    choices: list[str] = field(default_factory=list)
    allow_free_text: bool = True
    timeout_seconds: int = 120


class RunState:
    """Thread-safe transient state for a single run."""

    def __init__(self, run_id: str, session_id: str, model: str):
        self.run_id = run_id
        self.session_id = session_id
        self.model = model
        self.created_at_ms = int(time.time() * 1000)

        self._lock = threading.RLock()
        self._status: RunStatus = RunStatus.THINKING
        self._steer_queue: list[SteerMessage] = []
        self._pending_approval: Optional[ApprovalRequest] = None
        self._pending_clarify: Optional[ClarifyRequest] = None
        self._stop_requested = False
        self.service_verdict: Optional[dict[str, Any]] = None
        self._active_tool_call_id: Optional[str] = None
        self._active_tool: Optional[str] = None
        self._elapsed_ms: int = 0
        self._finish_reason: Optional[str] = None
        self._error_code: Optional[str] = None
        self._error_message: Optional[str] = None
        self._retryable: bool = False

    # --- Status transitions (transient; never touch prompt-cache baseline) ---

    def update_elapsed(self) -> int:
        self._elapsed_ms = int(time.monotonic() * 1000) - self.created_at_ms_offset
        return self._elapsed_ms

    @property
    def created_at_ms_offset(self) -> int:
        # monnotonic base so elapsed() is stable across calls
        return getattr(self, "_mbase", 0) or self._establish_mbase()

    def _establish_mbase(self) -> int:
        self._mbase = int(time.monotonic() * 1000)
        return self._mbase

    def set_status(self, status: RunStatus, **extra: Any) -> None:
        with self._lock:
            self._status = status
            if "finish_reason" in extra:
                self._finish_reason = extra["finish_reason"]
            if "error_code" in extra:
                self._error_code = extra["error_code"]
                self._error_message = extra.get("error_message")
                self._retryable = bool(extra.get("retryable", False))

    def status(self) -> RunStatus:
        with self._lock:
            return self._status

    # --- Steer queue ---

    def enqueue_steer(self, text: str) -> SteerMessage:
        msg = SteerMessage(text=text)
        with self._lock:
            self._steer_queue.append(msg)
        return msg

    def drain_steer(self) -> list[SteerMessage]:
        with self._lock:
            drained = self._steer_queue
            self._steer_queue = []
        return drained

    def steer_count(self) -> int:
        with self._lock:
            return len(self._steer_queue)

    def has_steer(self) -> bool:
        return self.steer_count() > 0

    def mark_steer_consumed(self, count: int = -1) -> None:
        with self._lock:
            if count < 0:
                self._steer_queue.clear()
            else:
                self._steer_queue = self._steer_queue[count:]

    # --- Approval ---

    def request_approval(self, approval: ApprovalRequest) -> None:
        with self._lock:
            self._pending_approval = approval
            self._status = RunStatus.AWAITING_APPROVAL

    def pending_approval(self) -> Optional[ApprovalRequest]:
        with self._lock:
            return self._pending_approval

    def clear_approval(self) -> None:
        with self._lock:
            self._pending_approval = None
            if self._status == RunStatus.AWAITING_APPROVAL:
                self._status = RunStatus.THINKING

    # --- Clarify ---

    def request_clarify(self, clarify: ClarifyRequest) -> None:
        with self._lock:
            self._pending_clarify = clarify
            self._status = RunStatus.AWAITING_CLARIFY

    def pending_clarify(self) -> Optional[ClarifyRequest]:
        with self._lock:
            return self._pending_clarify

    def clear_clarify(self) -> None:
        with self._lock:
            self._pending_clarify = None
            if self._status == RunStatus.AWAITING_CLARIFY:
                self._status = RunStatus.THINKING

    # --- Tool tracking ---

    def tool_running(self) -> tuple[Optional[str], Optional[str]]:
        with self._lock:
            return (self._active_tool_call_id, self._active_tool)

    def set_tool_running(self, tool_call_id: str, tool: str) -> None:
        with self._lock:
            self._active_tool_call_id = tool_call_id
            self._active_tool = tool
            self._status = RunStatus.TOOL_RUNNING

    def clear_tool(self) -> None:
        with self._lock:
            self._active_tool_call_id = None
            self._active_tool = None
            if self._status == RunStatus.TOOL_RUNNING:
                self._status = RunStatus.THINKING

    # --- Stop ---

    def request_stop(self) -> bool:
        """Returns True if the run is active and can be stopped."""
        with self._lock:
            if self._status in (RunStatus.FINISHED, RunStatus.FAILED, RunStatus.STOPPED):
                return False
            self._stop_requested = True
            return True

    def stop_requested(self) -> bool:
        with self._lock:
            return self._stop_requested

    def mark_stopped(self) -> None:
        with self._lock:
            self._stop_requested = True
            self._status = RunStatus.STOPPED

    # --- Snapshot for status responses / SSE reconciliations ---

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "run_id": self.run_id,
                "session_id": self.session_id,
                "model": self.model,
                "status": self._status.value,
                "elapsed_ms": self.update_elapsed(),
                "steer_pending": len(self._steer_queue),
                "has_pending_approval": self._pending_approval is not None,
                "has_pending_clarify": self._pending_clarify is not None,
                "stop_requested": self._stop_requested,
                "active_tool_call_id": self._active_tool_call_id,
                "active_tool": self._active_tool,
                "finish_reason": self._finish_reason,
                "error_code": self._error_code,
                "error_message": self._error_message,
                "retryable": self._retryable,
            }


class RunManager:
    """Registry of active runs, guarded by a single lock."""

    def __init__(self):
        self._lock = threading.RLock()
        self._runs: dict[str, RunState] = {}

    def create_run(self, session_id: str, model: str) -> RunState:
        run_id = uuid.uuid4().hex
        run = RunState(run_id=run_id, session_id=session_id, model=model)
        with self._lock:
            self._runs[run_id] = run
        return run

    def get(self, run_id: str) -> Optional[RunState]:
        with self._lock:
            return self._runs.get(run_id)

    def require(self, run_id: str, code: str = "RUN_NOT_FOUND") -> RunState:
        run = self.get(run_id)
        if run is None:
            raise KeyError(code)
        return run

    def remove(self, run_id: str) -> None:
        with self._lock:
            self._runs.pop(run_id, None)

    def list_active(self) -> list[str]:
        with self._lock:
            return [rid for rid, r in self._runs.items() if r.status() not in (
                RunStatus.FINISHED, RunStatus.FAILED, RunStatus.STOPPED,
            )]

    def clear_all(self) -> None:
        with self._lock:
            self._runs.clear()


_run_manager_instance: Optional[RunManager] = None
_run_manager_lock = threading.Lock()


def get_run_manager() -> RunManager:
    """Singleton accessor for the process-wide RunManager."""
    global _run_manager_instance
    if _run_manager_instance is None:
        with _run_manager_lock:
            if _run_manager_instance is None:
                _run_manager_instance = RunManager()
    return _run_manager_instance