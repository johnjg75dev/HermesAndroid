"""Extended SSE events for Android API server.

New event types beyond the standard gateway events:
- clarify.request/response
- moa.member.start/delta/done, moa.aggregate.start
- delegate attribution (parent_task_id/depth)
- device.progress
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum


class SSEEventType(Enum):
    """Extended SSE event types."""

    # Standard events (from gateway)
    MESSAGE_DELTA = "message_delta"
    TOOL_PROGRESS = "hermes.tool.progress"
    APPROVAL_REQUEST = "approval.request"
    APPROVAL_RESPONDED = "approval.responded"
    USAGE = "usage"
    FINISH = "finish"
    ERROR = "error"

    # New Android-specific events
    CLARIFY_REQUEST = "clarify.request"
    CLARIFY_RESPONSE = "clarify.response"
    MOA_MEMBER_START = "moa.member.start"
    MOA_MEMBER_DELTA = "moa.member.delta"
    MOA_MEMBER_DONE = "moa.member.done"
    MOA_AGGREGATE_START = "moa.aggregate.start"
    DELEGATE_START = "delegate.start"
    DELEGATE_DONE = "delegate.done"
    DEVICE_PROGRESS = "device.progress"


@dataclass
class SSEEvent:
    """Base SSE event."""

    event: str
    data: dict[str, Any]
    run_id: str
    timestamp: float

    def to_sse(self) -> str:
        """Format as SSE message."""
        import json
        lines = [
            f"event: {self.event}",
            f"data: {json.dumps(self.data, separators=(',', ':'))}",
            "",
        ]
        return "\n".join(lines)


@dataclass
class ClarifyRequestEvent(SSEEvent):
    """Clarify request event (mirrors approval)."""

    def __init__(
        self,
        run_id: str,
        prompt: str,
        choices: list[str] | None = None,
        allow_free_text: bool = True,
        timeout_seconds: int = 120,
    ):
        super().__init__(
            event=SSEEventType.CLARIFY_REQUEST.value,
            data={
                "prompt": prompt,
                "choices": choices or [],
                "allow_free_text": allow_free_text,
                "timeout_seconds": timeout_seconds,
            },
            run_id=run_id,
            timestamp=0,  # Set by emitter
        )


@dataclass
class MOAMemberStartEvent(SSEEvent):
    """MoA member started."""

    def __init__(self, run_id: str, member_index: int, model: str, task: str):
        super().__init__(
            event=SSEEventType.MOA_MEMBER_START.value,
            data={
                "member_index": member_index,
                "model": model,
                "task": task,
            },
            run_id=run_id,
            timestamp=0,
        )


@dataclass
class MOAMemberDeltaEvent(SSEEvent):
    """MoA member streaming delta."""

    def __init__(self, run_id: str, member_index: int, delta: str):
        super().__init__(
            event=SSEEventType.MOA_MEMBER_DELTA.value,
            data={
                "member_index": member_index,
                "delta": delta,
            },
            run_id=run_id,
            timestamp=0,
        )


@dataclass
class MOAMemberDoneEvent(SSEEvent):
    """MoA member completed."""

    def __init__(
        self,
        run_id: str,
        member_index: int,
        content: str,
        success: bool,
        error: Optional[str] = None,
    ):
        super().__init__(
            event=SSEEventType.MOA_MEMBER_DONE.value,
            data={
                "member_index": member_index,
                "content": content,
                "success": success,
                "error": error,
            },
            run_id=run_id,
            timestamp=0,
        )


@dataclass
class MOAAggregateStartEvent(SSEEvent):
    """MoA aggregation started."""

    def __init__(self, run_id: str, aggregator_model: str, member_count: int):
        super().__init__(
            event=SSEEventType.MOA_AGGREGATE_START.value,
            data={
                "aggregator_model": aggregator_model,
                "member_count": member_count,
            },
            run_id=run_id,
            timestamp=0,
        )


@dataclass
class DelegateStartEvent(SSEEvent):
    """Delegation started."""

    def __init__(
        self,
        run_id: str,
        parent_task_id: str,
        depth: int,
        goal: str,
    ):
        super().__init__(
            event=SSEEventType.DELEGATE_START.value,
            data={
                "parent_task_id": parent_task_id,
                "depth": depth,
                "goal": goal,
            },
            run_id=run_id,
            timestamp=0,
        )


@dataclass
class DelegateDoneEvent(SSEEvent):
    """Delegation completed."""

    def __init__(
        self,
        run_id: str,
        parent_task_id: str,
        depth: int,
        summary: str,
        success: bool,
    ):
        super().__init__(
            event=SSEEventType.DELEGATE_DONE.value,
            data={
                "parent_task_id": parent_task_id,
                "depth": depth,
                "summary": summary,
                "success": success,
            },
            run_id=run_id,
            timestamp=0,
        )


@dataclass
class DeviceProgressEvent(SSEEvent):
    """Long-running device operation progress."""

    def __init__(
        self,
        run_id: str,
        tool_call_id: str,
        operation: str,
        progress: float,  # 0.0 - 1.0
        message: str = "",
    ):
        super().__init__(
            event=SSEEventType.DEVICE_PROGRESS.value,
            data={
                "tool_call_id": tool_call_id,
                "operation": operation,
                "progress": progress,
                "message": message,
            },
            run_id=run_id,
            timestamp=0,
        )


# --- Event factory for easy creation ---

def create_clarify_request(
    run_id: str,
    prompt: str,
    choices: list[str] | None = None,
    allow_free_text: bool = True,
    timeout_seconds: int = 120,
) -> SSEEvent:
    return ClarifyRequestEvent(run_id, prompt, choices, allow_free_text, timeout_seconds)


def create_moa_member_start(
    run_id: str,
    member_index: int,
    model: str,
    task: str,
) -> SSEEvent:
    return MOAMemberStartEvent(run_id, member_index, model, task)


def create_moa_member_delta(
    run_id: str,
    member_index: int,
    delta: str,
) -> SSEEvent:
    return MOAMemberDeltaEvent(run_id, member_index, delta)


def create_moa_member_done(
    run_id: str,
    member_index: int,
    content: str,
    success: bool,
    error: Optional[str] = None,
) -> SSEEvent:
    return MOAMemberDoneEvent(run_id, member_index, content, success, error)


def create_moa_aggregate_start(
    run_id: str,
    aggregator_model: str,
    member_count: int,
) -> SSEEvent:
    return MOAAggregateStartEvent(run_id, aggregator_model, member_count)


def create_delegate_start(
    run_id: str,
    parent_task_id: str,
    depth: int,
    goal: str,
) -> SSEEvent:
    return DelegateStartEvent(run_id, parent_task_id, depth, goal)


def create_delegate_done(
    run_id: str,
    parent_task_id: str,
    depth: int,
    summary: str,
    success: bool,
) -> SSEEvent:
    return DelegateDoneEvent(run_id, parent_task_id, depth, summary, success)


def create_device_progress(
    run_id: str,
    tool_call_id: str,
    operation: str,
    progress: float,
    message: str = "",
) -> SSEEvent:
    return DeviceProgressEvent(run_id, tool_call_id, operation, progress, message)