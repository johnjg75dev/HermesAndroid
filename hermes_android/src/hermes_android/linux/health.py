"""30-second health tick for Linux subsystem."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from hermes_android.linux.base import HealthStatus, LinuxSubsystem, SubsystemInfo


@dataclass
class HealthEvent:
    """Health check event."""

    subsystem: str
    status: HealthStatus
    info: SubsystemInfo
    timestamp: float


class LinuxHealthMonitor:
    """Monitors Linux subsystem health with periodic ticks."""

    def __init__(
        self,
        subsystem: LinuxSubsystem,
        interval: float = 30.0,
        callback: Optional[Callable[[HealthEvent], None]] = None,
    ):
        self._subsystem = subsystem
        self._interval = interval
        self._callback = callback
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Start the health monitor."""
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="hermes-linux-health",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the health monitor."""
        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)

    def _run(self) -> None:
        """Background health check loop."""
        while self._running and not self._stop_event.is_set():
            try:
                info = self._subsystem.probe()
                event = HealthEvent(
                    subsystem=self._subsystem.execution_mode.value,
                    status=info.health,
                    info=info,
                    timestamp=time.time(),
                )
                if self._callback:
                    self._callback(event)
            except Exception:
                pass  # Log but don't crash

            self._stop_event.wait(self._interval)

    def check_now(self) -> HealthEvent:
        """Perform an immediate health check."""
        info = self._subsystem.probe()
        return HealthEvent(
            subsystem=self._subsystem.execution_mode.value,
            status=info.health,
            info=info,
            timestamp=time.time(),
        )