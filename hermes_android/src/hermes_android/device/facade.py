"""Device facade protocol - typed interface for agent → Kotlin calls.

This replaces ~30 ad-hoc Hermes*Bridge.kt classes with a single
typed protocol. Called from agent executor threads; Kotlin dispatches
internally with bounded timeouts and cancellation via run_id.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class FacadeResult:
    """Result from a facade call."""

    success: bool
    data: Any = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    @classmethod
    def ok(cls, data: Any = None) -> "FacadeResult":
        return cls(success=True, data=data)

    @classmethod
    def err(cls, code: str, message: str) -> "FacadeResult":
        return cls(success=False, error_code=code, error_message=message)


class DeviceFacade(ABC):
    """
    Typed protocol for device capabilities.

    Each method corresponds to a tool the agent can invoke.
    Kotlin implements this interface and registers it via FacadeRegistry.
    """

    # --- Terminal / Process ---

    @abstractmethod
    def terminal_exec(
        self,
        command: str,
        timeout_seconds: int = 30,
        run_id: Optional[str] = None,
    ) -> FacadeResult:
        """Execute a shell command."""
        pass

    @abstractmethod
    def terminal_spawn(
        self,
        command: str,
        cwd: Optional[str] = None,
        env: Optional[dict[str, str]] = None,
        run_id: Optional[str] = None,
    ) -> FacadeResult:
        """Spawn a background process, return PID."""
        pass

    @abstractmethod
    def terminal_kill(
        self,
        pid: int,
        run_id: Optional[str] = None,
    ) -> FacadeResult:
        """Kill a spawned process."""
        pass

    @abstractmethod
    def terminal_list(self, run_id: Optional[str] = None) -> FacadeResult:
        """List active terminal sessions."""
        pass

    # --- File I/O ---

    @abstractmethod
    def file_read(
        self,
        path: str,
        max_chars: int = 100_000,
        run_id: Optional[str] = None,
    ) -> FacadeResult:
        """Read a file."""
        pass

    @abstractmethod
    def file_write(
        self,
        path: str,
        content: str,
        append: bool = False,
        run_id: Optional[str] = None,
    ) -> FacadeResult:
        """Write a file."""
        pass

    @abstractmethod
    def file_list(
        self,
        path: str,
        recursive: bool = False,
        run_id: Optional[str] = None,
    ) -> FacadeResult:
        """List directory contents."""
        pass

    @abstractmethod
    def file_delete(
        self,
        path: str,
        run_id: Optional[str] = None,
    ) -> FacadeResult:
        """Delete a file or directory."""
        pass

    @abstractmethod
    def file_search(
        self,
        path: str,
        pattern: str,
        run_id: Optional[str] = None,
    ) -> FacadeResult:
        """Search for files matching pattern."""
        pass

    # --- System ---

    @abstractmethod
    def system_info(self, run_id: Optional[str] = None) -> FacadeResult:
        """Get system information."""
        pass

    @abstractmethod
    def system_action(
        self,
        action: str,
        args: Optional[dict[str, Any]] = None,
        run_id: Optional[str] = None,
    ) -> FacadeResult:
        """Perform a system action (WiFi, Bluetooth, etc.)."""
        pass

    # --- Accessibility ---

    @abstractmethod
    def accessibility_snapshot(
        self,
        limit: int = 80,
        run_id: Optional[str] = None,
    ) -> FacadeResult:
        """Get UI accessibility snapshot."""
        pass

    @abstractmethod
    def accessibility_action(
        self,
        action: str,
        **kwargs: Any,
    ) -> FacadeResult:
        """Perform accessibility action (click, scroll, etc.)."""
        pass

    # --- Projection / Screen ---

    @abstractmethod
    def projection_start(
        self,
        run_id: Optional[str] = None,
    ) -> FacadeResult:
        """Start MediaProjection (requires consent)."""
        pass

    @abstractmethod
    def projection_stop(self, run_id: Optional[str] = None) -> FacadeResult:
        """Stop MediaProjection."""
        pass

    @abstractmethod
    def projection_screenshot(
        self,
        run_id: Optional[str] = None,
    ) -> FacadeResult:
        """Take screenshot via MediaProjection."""
        pass

    # --- Sensors / Location ---

    @abstractmethod
    def sensors_list(self, run_id: Optional[str] = None) -> FacadeResult:
        """List available sensors."""
        pass

    @abstractmethod
    def sensors_read(
        self,
        sensor_type: str,
        run_id: Optional[str] = None,
    ) -> FacadeResult:
        """Read sensor data."""
        pass

    @abstractmethod
    def location_get(
        self,
        run_id: Optional[str] = None,
    ) -> FacadeResult:
        """Get current location."""
        pass

    # --- Calendar / Logcat / Notifications ---

    @abstractmethod
    def calendar_query(
        self,
        query: str,
        run_id: Optional[str] = None,
    ) -> FacadeResult:
        """Query calendar."""
        pass

    @abstractmethod
    def logcat_read(
        self,
        filter_spec: str = "",
        max_lines: int = 100,
        run_id: Optional[str] = None,
    ) -> FacadeResult:
        """Read logcat."""
        pass

    @abstractmethod
    def notifications_list(
        self,
        limit: int = 50,
        run_id: Optional[str] = None,
    ) -> FacadeResult:
        """List recent notifications."""
        pass

    # --- Clipboard / Share ---

    @abstractmethod
    def clipboard_get(self, run_id: Optional[str] = None) -> FacadeResult:
        """Get clipboard content."""
        pass

    @abstractmethod
    def clipboard_set(
        self,
        content: str,
        run_id: Optional[str] = None,
    ) -> FacadeResult:
        """Set clipboard content."""
        pass

    @abstractmethod
    def share_send(
        self,
        content: str,
        mime_type: str = "text/plain",
        run_id: Optional[str] = None,
    ) -> FacadeResult:
        """Share content via Android share sheet."""
        pass

    # --- TTS / STT ---

    @abstractmethod
    def tts_speak(
        self,
        text: str,
        language: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> FacadeResult:
        """Text-to-speech."""
        pass

    @abstractmethod
    def stt_listen(
        self,
        language: Optional[str] = None,
        timeout_seconds: int = 30,
        run_id: Optional[str] = None,
    ) -> FacadeResult:
        """Speech-to-text."""
        pass

    # --- Notifications ---

    @abstractmethod
    def notification_post(
        self,
        title: str,
        body: str,
        channel: str = "hermes",
        run_id: Optional[str] = None,
    ) -> FacadeResult:
        """Post a notification."""
        pass

    # --- Apps ---

    @abstractmethod
    def apps_list(
        self,
        run_id: Optional[str] = None,
    ) -> FacadeResult:
        """List installed apps."""
        pass

    @abstractmethod
    def apps_launch(
        self,
        package_name: str,
        run_id: Optional[str] = None,
    ) -> FacadeResult:
        """Launch an app."""
        pass

    # --- Resources ---

    @abstractmethod
    def resources_get(
        self,
        run_id: Optional[str] = None,
    ) -> FacadeResult:
        """Get resource usage (RAM, CPU, etc.)."""
        pass

    # --- Cleanup ---

    @abstractmethod
    def cleanup_run(
        self,
        components: Optional[list[str]] = None,
        run_id: Optional[str] = None,
    ) -> FacadeResult:
        """Run cleanup (GC, cache trim, etc.)."""
        pass


# --- Python-side stub for testing ---

class _StubFacade(DeviceFacade):
    """Stub implementation for non-Android environments."""

    def _stub(self, method: str) -> FacadeResult:
        return FacadeResult.err(
            "DEVICE_UNAVAILABLE",
            f"Device facade not available (stub): {method}",
        )

    def terminal_exec(self, command: str, timeout_seconds: int = 30, run_id: Optional[str] = None) -> FacadeResult:
        return self._stub("terminal_exec")

    def terminal_spawn(self, command: str, cwd: Optional[str] = None, env: Optional[dict[str, str]] = None, run_id: Optional[str] = None) -> FacadeResult:
        return self._stub("terminal_spawn")

    def terminal_kill(self, pid: int, run_id: Optional[str] = None) -> FacadeResult:
        return self._stub("terminal_kill")

    def terminal_list(self, run_id: Optional[str] = None) -> FacadeResult:
        return self._stub("terminal_list")

    def file_read(self, path: str, max_chars: int = 100_000, run_id: Optional[str] = None) -> FacadeResult:
        return self._stub("file_read")

    def file_write(self, path: str, content: str, append: bool = False, run_id: Optional[str] = None) -> FacadeResult:
        return self._stub("file_write")

    def file_list(self, path: str, recursive: bool = False, run_id: Optional[str] = None) -> FacadeResult:
        return self._stub("file_list")

    def file_delete(self, path: str, run_id: Optional[str] = None) -> FacadeResult:
        return self._stub("file_delete")

    def file_search(self, path: str, pattern: str, run_id: Optional[str] = None) -> FacadeResult:
        return self._stub("file_search")

    def system_info(self, run_id: Optional[str] = None) -> FacadeResult:
        return self._stub("system_info")

    def system_action(self, action: str, args: Optional[dict[str, Any]] = None, run_id: Optional[str] = None) -> FacadeResult:
        return self._stub("system_action")

    def accessibility_snapshot(self, limit: int = 80, run_id: Optional[str] = None) -> FacadeResult:
        return self._stub("accessibility_snapshot")

    def accessibility_action(self, action: str, **kwargs: Any) -> FacadeResult:
        return self._stub("accessibility_action")

    def projection_start(self, run_id: Optional[str] = None) -> FacadeResult:
        return self._stub("projection_start")

    def projection_stop(self, run_id: Optional[str] = None) -> FacadeResult:
        return self._stub("projection_stop")

    def projection_screenshot(self, run_id: Optional[str] = None) -> FacadeResult:
        return self._stub("projection_screenshot")

    def sensors_list(self, run_id: Optional[str] = None) -> FacadeResult:
        return self._stub("sensors_list")

    def sensors_read(self, sensor_type: str, run_id: Optional[str] = None) -> FacadeResult:
        return self._stub("sensors_read")

    def location_get(self, run_id: Optional[str] = None) -> FacadeResult:
        return self._stub("location_get")

    def calendar_query(self, query: str, run_id: Optional[str] = None) -> FacadeResult:
        return self._stub("calendar_query")

    def logcat_read(self, filter_spec: str = "", max_lines: int = 100, run_id: Optional[str] = None) -> FacadeResult:
        return self._stub("logcat_read")

    def notifications_list(self, limit: int = 50, run_id: Optional[str] = None) -> FacadeResult:
        return self._stub("notifications_list")

    def clipboard_get(self, run_id: Optional[str] = None) -> FacadeResult:
        return self._stub("clipboard_get")

    def clipboard_set(self, content: str, run_id: Optional[str] = None) -> FacadeResult:
        return self._stub("clipboard_set")

    def share_send(self, content: str, mime_type: str = "text/plain", run_id: Optional[str] = None) -> FacadeResult:
        return self._stub("share_send")

    def tts_speak(self, text: str, language: Optional[str] = None, run_id: Optional[str] = None) -> FacadeResult:
        return self._stub("tts_speak")

    def stt_listen(self, language: Optional[str] = None, timeout_seconds: int = 30, run_id: Optional[str] = None) -> FacadeResult:
        return self._stub("stt_listen")

    def notification_post(self, title: str, body: str, channel: str = "hermes", run_id: Optional[str] = None) -> FacadeResult:
        return self._stub("notification_post")

    def apps_list(self, run_id: Optional[str] = None) -> FacadeResult:
        return self._stub("apps_list")

    def apps_launch(self, package_name: str, run_id: Optional[str] = None) -> FacadeResult:
        return self._stub("apps_launch")

    def resources_get(self, run_id: Optional[str] = None) -> FacadeResult:
        return self._stub("resources_get")

    def cleanup_run(self, components: Optional[list[str]] = None, run_id: Optional[str] = None) -> FacadeResult:
        return self._stub("cleanup_run")


# Global stub instance for non-Android testing
STUB_FACADE = _StubFacade()