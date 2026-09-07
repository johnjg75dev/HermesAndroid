"""RuntimeService — THE Kotlin entry point (PyObject).

This is the single PyObject that Kotlin holds via Chaquopy. All lifecycle
operations (start, stop, status, bootstrap) go through this service.
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from hermes_android.errors import (
    HermesError,
    HermesRuntimeError,
    BOOT_FATAL_PHASE_FAILED,
    BOOT_PHASE_FAILED,
    RUNTIME_ALREADY_RUNNING,
    RUNTIME_NOT_STARTED,
    RUNTIME_START_FAILED,
    RUNTIME_STOP_FAILED,
)
from hermes_android.runtime.bootstrap import BootstrapOrchestrator, BootPhase
from hermes_android.runtime.lifecycle import RuntimeLifecycle


@dataclass(frozen=True)
class RuntimeStatus:
    """Runtime status snapshot for Kotlin."""

    started: bool
    boot_phase: str
    boot_progress: float  # 0.0 - 1.0
    base_url: Optional[str] = None
    hermes_home: Optional[str] = None
    model_name: Optional[str] = None
    error: Optional[str] = None
    probe_result: Optional[str] = None


class RuntimeService:
    """
    Main entry point for Kotlin via Chaquopy (PyObject).

    Usage from Kotlin:
        val service = Python.getInstance().getModule("hermes_android.runtime.service")
            .callAttr("RuntimeService")
        val status = service.start(filesDir, port, key, modelName)
        // ... later ...
        service.stop()
    """

    def __init__(self):
        self._lifecycle = RuntimeLifecycle()
        self._bootstrap: Optional[BootstrapOrchestrator] = None
        self._status_lock = threading.Lock()
        self._current_status = RuntimeStatus(
            started=False,
            boot_phase="idle",
            boot_progress=0.0,
        )

    # --- Public API for Kotlin ---

    def start(
        self,
        files_dir: str,
        *,
        api_server_port: int | None = None,
        api_server_key: str | None = None,
        api_server_model_name: str = "hermes-agent-android",
    ) -> dict[str, Any]:
        """Start the runtime. Returns status dict."""
        with self._status_lock:
            if self._lifecycle.is_running():
                raise HermesRuntimeError(RUNTIME_ALREADY_RUNNING)

        try:
            self._bootstrap = BootstrapOrchestrator(
                files_dir=files_dir,
                api_server_port=api_server_port,
                api_server_key=api_server_key,
                api_server_model_name=api_server_model_name,
                progress_callback=self._on_boot_progress,
            )
            self._bootstrap.run()
            runtime_info = self._bootstrap.runtime_info

            self._lifecycle.start(runtime_info)

            with self._status_lock:
                self._current_status = RuntimeStatus(
                    started=True,
                    boot_phase="ready",
                    boot_progress=1.0,
                    base_url=runtime_info.base_url,
                    hermes_home=str(runtime_info.hermes_home),
                    model_name=runtime_info.model_name,
                    probe_result=runtime_info.probe_result,
                )
            return self._current_status.__dict__

        except HermesError:
            raise
        except Exception as e:
            with self._status_lock:
                self._current_status = RuntimeStatus(
                    started=False,
                    boot_phase="failed",
                    boot_progress=0.0,
                    error=str(e),
                )
            raise HermesRuntimeError(RUNTIME_START_FAILED, cause=e)

    def stop(self) -> dict[str, Any]:
        """Stop the runtime. Returns status dict."""
        with self._status_lock:
            if not self._lifecycle.is_running():
                raise HermesRuntimeError(RUNTIME_NOT_STARTED)

        try:
            self._lifecycle.stop()
            with self._status_lock:
                self._current_status = RuntimeStatus(
                    started=False,
                    boot_phase="stopped",
                    boot_progress=0.0,
                )
            return self._current_status.__dict__
        except Exception as e:
            raise HermesRuntimeError(RUNTIME_STOP_FAILED, cause=e)

    def status(self) -> dict[str, Any]:
        """Get current runtime status."""
        with self._status_lock:
            return self._current_status.__dict__

    def restart(self) -> dict[str, Any]:
        """Restart the runtime (profile switch handshake)."""
        self.stop()
        # Note: Kotlin must re-call start() with new profile params
        return self.status()

    def health_check(self) -> dict[str, Any]:
        """Health check endpoint for /health/detailed."""
        with self._status_lock:
            return {
                "started": self._current_status.started,
                "boot_phase": self._current_status.boot_phase,
                "base_url": self._current_status.base_url,
            }

    # --- Internal ---

    def _on_boot_progress(self, phase: BootPhase, progress: float, error: Optional[str] = None):
        """Callback from bootstrap orchestrator."""
        with self._status_lock:
            self._current_status = RuntimeStatus(
                started=False,
                boot_phase=phase.name.lower(),
                boot_progress=progress,
                error=error,
            )