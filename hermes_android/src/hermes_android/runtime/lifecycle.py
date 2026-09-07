"""asyncio-loop ownership and restart handshake for the Android runtime."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from hermes_android.errors import (
    HermesError,
    HermesRuntimeError,
    RUNTIME_ALREADY_RUNNING,
    RUNTIME_NOT_STARTED,
    RUNTIME_STOP_FAILED,
)


@dataclass(frozen=True)
class RuntimeInfo:
    """Runtime information passed from bootstrap to lifecycle."""

    files_dir: Path
    hermes_home: Path
    api_server_host: str
    api_server_port: int
    api_server_key: str
    api_server_model_name: str
    base_url: str
    probe_result: str
    linux_execution_mode: str


class RuntimeLifecycle:
    """
    Owns the asyncio event loop and API server lifecycle.

    Runs on a dedicated daemon thread. All async operations are scheduled
    via run_coroutine_threadsafe.
    """

    def __init__(self):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._handle: Any = None  # AndroidServerHandle
        self._runtime_info: Optional[RuntimeInfo] = None
        self._lock = threading.Lock()

    def is_running(self) -> bool:
        with self._lock:
            return self._loop is not None and self._loop.is_running()

    def start(self, runtime_info: RuntimeInfo) -> None:
        """Start the lifecycle with bootstrapped runtime info."""
        with self._lock:
            if self.is_running():
                raise HermesRuntimeError(RUNTIME_ALREADY_RUNNING)

            self._runtime_info = runtime_info

            # Create new event loop in a dedicated thread
            self._loop = asyncio.new_event_loop()

            def _run_loop():
                asyncio.set_event_loop(self._loop)
                self._loop.run_forever()
                self._loop.run_until_complete(self._loop.shutdown_asyncgens())
                self._loop.close()

            self._thread = threading.Thread(
                target=_run_loop,
                name="hermes-android-runtime",
                daemon=True,
            )
            self._thread.start()

            # Wait for loop to be ready
            while not self._loop.is_running():
                threading.Event().wait(0.01)

            # Start the API server on the loop
            future = asyncio.run_coroutine_threadsafe(
                self._async_start_server(), self._loop
            )
            future.result(timeout=30.0)

    async def _async_start_server(self) -> None:
        """Async server startup on the event loop."""
        from hermes_android.runtime.server import AndroidServerHandle, _platform_config
        from gateway.config import PlatformConfig

        runtime = self._runtime_info
        assert runtime is not None

        adapter_config = _platform_config(runtime)

        # Import APIServerAdapter here to avoid circular imports
        from gateway.platforms.api_server import APIServerAdapter

        adapter = APIServerAdapter(adapter_config)
        await adapter.connect()

        self._handle = AndroidServerHandle(
            runtime=runtime,
            adapter=adapter,
            loop=self._loop,
            thread=self._thread,
        )

    def stop(self) -> None:
        """Stop the runtime gracefully."""
        with self._lock:
            if not self.is_running():
                raise HermesRuntimeError(RUNTIME_NOT_STARTED)

            loop = self._loop
            handle = self._handle
            thread = self._thread

            if handle is not None and loop is not None:
                future = asyncio.run_coroutine_threadsafe(handle.adapter.disconnect(), loop)
                try:
                    future.result(timeout=10.0)
                except Exception:
                    pass  # Best effort

            if loop is not None:
                loop.call_soon_threadsafe(loop.stop)

            if thread is not None:
                thread.join(timeout=5.0)

            self._loop = None
            self._thread = None
            self._handle = None
            self._runtime_info = None

    def restart_handshake(self) -> None:
        """Signal readiness for profile-switch restart handshake."""
        # Called by Kotlin before stop() when switching profiles
        # Ensures clean state for next start()
        with self._lock:
            if self._handle is not None and self._loop is not None:
                future = asyncio.run_coroutine_threadsafe(
                    self._handle.adapter.disconnect(), self._loop
                )
                try:
                    future.result(timeout=5.0)
                except Exception:
                    pass

    @property
    def base_url(self) -> Optional[str]:
        with self._lock:
            if self._handle:
                return self._handle.base_url
        return None

    @property
    def runtime_info(self) -> Optional[RuntimeInfo]:
        with self._lock:
            return self._runtime_info