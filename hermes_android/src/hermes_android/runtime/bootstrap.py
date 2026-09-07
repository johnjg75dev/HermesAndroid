"""9-phase bootstrap orchestrator for Hermes Android runtime.

Phases (with failure semantics):
1. profile      — FATAL: set HERMES_HOME, load profile
2. interpreter  — FATAL: ensure Python/Chaquopy ready, sys.path shim
3. config       — FATAL: load config.yaml, apply Android defaults
4. assets       — DEGRADED: delta-sync bundled skills/assets (read-only if fails)
5. linux        — DEGRADED: probe Linux subsystem (embedded/proot/termux)
6. mcp          — DEGRADED: sync MCP config
7. memory       — DEGRADED: initialize memory providers
8. api          — FATAL: start API server (aiohttp)
9. ready        — FINAL: emit ready event

Each phase emits `boot.phase` event with timing.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from hermes_android.errors import (
    HermesError,
    HermesRuntimeError,
    BOOT_FATAL_PHASE_FAILED,
    BOOT_PHASE_FAILED,
)
from hermes_android.runtime.lifecycle import RuntimeInfo

__all__ = [
    "BootPhase",
    "BootstrapOrchestrator",
    "RuntimeInfo",
    "bootstrap_android_runtime",
    "boot_phase_report",
    "last_boot_orchestrator",
]

# Orchestrator from the most recent bootstrap on this process. The embedded
# runtime boots once per interpreter; Kotlin reads the phase checklist via
# server_bridge/RuntimeService payloads.
_last_orchestrator: Optional["BootstrapOrchestrator"] = None


def last_boot_orchestrator() -> Optional["BootstrapOrchestrator"]:
    return _last_orchestrator


def boot_phase_report() -> list[dict[str, Any]]:
    """Phase checklist of the most recent bootstrap ([] before first boot)."""
    orchestrator = _last_orchestrator
    return orchestrator.phase_results if orchestrator is not None else []


class BootPhase(Enum):
    """Boot phases in order."""

    PROFILE = ("profile", True)
    INTERPRETER = ("interpreter", True)
    CONFIG = ("config", True)
    ASSETS = ("assets", False)
    LINUX = ("linux", False)
    MCP = ("mcp", False)
    MEMORY = ("memory", False)
    API = ("api", True)
    READY = ("ready", True)

    def __init__(self, name: str, fatal: bool):
        self.phase_name = name
        self.fatal = fatal


class BootstrapOrchestrator:
    """Orchestrates the 9-phase boot sequence."""

    def __init__(
        self,
        files_dir: str,
        *,
        api_server_port: int | None = None,
        api_server_key: str | None = None,
        api_server_model_name: str = "hermes-agent-android",
        progress_callback: Optional[Callable[[BootPhase, float, Optional[str]], None]] = None,
    ):
        self.files_dir = Path(files_dir).expanduser().resolve()
        self.api_server_port = api_server_port
        self.api_server_key = api_server_key
        self.api_server_model_name = api_server_model_name
        self._progress_callback = progress_callback
        self._runtime_info: Optional[RuntimeInfo] = None
        self._phase_timings: dict[str, float] = {}
        self._phase_results: list[dict[str, Any]] = []
        self._runtime_prepared = False

    @property
    def phase_results(self) -> list[dict[str, Any]]:
        """Per-phase outcome records for M01-style boot reporting."""
        return [dict(item) for item in self._phase_results]

    @property
    def runtime_info(self) -> RuntimeInfo:
        if self._runtime_info is None:
            raise RuntimeError("Bootstrap not completed")
        return self._runtime_info

    @property
    def phase_timings(self) -> dict[str, float]:
        return dict(self._phase_timings)

    def run_preparation_phases(self) -> None:
        """Run phases 1-7 (everything except API/ready). Never binds sockets."""
        self._run_phase(BootPhase.PROFILE, self._phase_profile)
        self._run_phase(BootPhase.INTERPRETER, self._phase_interpreter)
        self._run_phase(BootPhase.CONFIG, self._phase_config)
        self._run_phase(BootPhase.ASSETS, self._phase_assets)
        self._run_phase(BootPhase.LINUX, self._phase_linux)
        self._run_phase(BootPhase.MCP, self._phase_mcp)
        self._run_phase(BootPhase.MEMORY, self._phase_memory)
        # RuntimeInfo is needed by callers even without the server running.
        self._run_phase(BootPhase.API, self._phase_api)
        self._runtime_prepared = True

    def run(self) -> None:
        """Execute all boot phases sequentially."""
        start_total = time.monotonic()

        # Phase 1: Profile
        self._run_phase(BootPhase.PROFILE, self._phase_profile)

        # Phase 2: Interpreter
        self._run_phase(BootPhase.INTERPRETER, self._phase_interpreter)

        # Phase 3: Config
        self._run_phase(BootPhase.CONFIG, self._phase_config)

        # Phase 4: Assets (degraded-continue)
        self._run_phase(BootPhase.ASSETS, self._phase_assets)

        # Phase 5: Linux (degraded-continue)
        self._run_phase(BootPhase.LINUX, self._phase_linux)

        # Phase 6: MCP (degraded-continue)
        self._run_phase(BootPhase.MCP, self._phase_mcp)

        # Phase 7: Memory (degraded-continue)
        self._run_phase(BootPhase.MEMORY, self._phase_memory)

        # Phase 8: API (fatal)
        self._run_phase(BootPhase.API, self._phase_api)

        # Phase 9: Ready
        self._run_phase(BootPhase.READY, self._phase_ready)

        total_time = time.monotonic() - start_total
        self._phase_timings["total"] = total_time

    def _run_phase(
        self,
        phase: BootPhase,
        phase_fn: Callable[[], None],
    ) -> None:
        """Run a single phase with timing and error handling."""
        start = time.monotonic()
        error_msg: Optional[str] = None
        status = "ok"

        try:
            self._emit_progress(phase, 0.0)
            phase_fn()
            self._emit_progress(phase, 1.0)
        except HermesError as e:
            error_msg = str(e)
            if phase.fatal:
                status = "failed"
                raise HermesRuntimeError(
                    BOOT_FATAL_PHASE_FAILED,
                    f"Fatal phase {phase.phase_name} failed: {e}",
                    details={"phase": phase.phase_name, "original_error": e.code},
                    cause=e,
                )
            else:
                # Degraded-continue: log and proceed
                status = "degraded"
                self._emit_progress(phase, 1.0, error_msg)
        except Exception as e:
            error_msg = str(e)
            if phase.fatal:
                status = "failed"
                raise HermesRuntimeError(
                    BOOT_FATAL_PHASE_FAILED,
                    f"Fatal phase {phase.phase_name} failed: {e}",
                    details={"phase": phase.phase_name},
                    cause=e,
                )
            else:
                status = "degraded"
                self._emit_progress(phase, 1.0, error_msg)
        finally:
            duration_ms = round((time.monotonic() - start) * 1000.0, 1)
            self._phase_timings[phase.phase_name] = time.monotonic() - start
            self._phase_results.append({
                "phase": phase.phase_name,
                "fatal": phase.fatal,
                "status": status if not (status == "ok" and phase is BootPhase.READY) else "ready",
                "error": error_msg,
                "duration_ms": duration_ms,
            })

    def _emit_progress(self, phase: BootPhase, progress: float, error: Optional[str] = None):
        if self._progress_callback:
            self._progress_callback(phase, progress, error)

    # --- Phase implementations ---

    def _phase_profile(self) -> None:
        """Phase 1: Set up HERMES_HOME for the active profile."""
        from hermes_android.profile.manager import ProfileManager

        profile_mgr = ProfileManager()
        profile_mgr.ensure_active_profile(self.files_dir)

    def _phase_interpreter(self) -> None:
        """Phase 2: Ensure Python/Chaquopy interpreter readiness."""
        # Chaquopy-specific: prefer_hermes_package_root puts our wheel first
        from hermes_android.python_path import prefer_hermes_package_root
        prefer_hermes_package_root()

    def _phase_config(self) -> None:
        """Phase 3: Load config.yaml, apply Android defaults."""
        from hermes_android.config.defaults import ensure_android_defaults
        ensure_android_defaults(persist=True)

    def _phase_assets(self) -> None:
        """Phase 4: Delta-sync bundled skills/assets (read-only fallback)."""
        from hermes_android.assets.bundled import sync_bundled_skills, configure_skill_env
        configure_skill_env()
        sync_bundled_skills(quiet=True)

    def _phase_linux(self) -> None:
        """Phase 5: Probe Linux subsystem (embedded/proot/termux)."""
        from hermes_android.linux.base import LinuxSubsystemFactory

        factory = LinuxSubsystemFactory(self.files_dir)
        subsystem = factory.create_subsystem()
        subsystem.probe()
        # Store execution mode for later
        self._linux_execution_mode = subsystem.execution_mode

    def _phase_mcp(self) -> None:
        """Phase 6: Sync MCP config to runtime."""
        from hermes_android.mcp.sync import sync_android_mcp_config
        from hermes_android.runtime.env import hermes_home_for

        sync_android_mcp_config(hermes_home_for(self.files_dir))

    def _phase_memory(self) -> None:
        """Phase 7: Initialize memory providers (post_setup flows)."""
        # Memory providers initialize lazily via post_setup when first used
        # This phase just ensures the manager is importable
        from agent.memory_manager import MemoryManager  # noqa: F401

    def _phase_api(self) -> None:
        """Phase 8: Resolve runtime env + build RuntimeInfo.

        The API server itself is started by RuntimeLifecycle.start() on its own
        event loop — this phase only prepares the environment so that the port,
        key, and HERMES_HOME are pinned before Kotlin talks to the loopback.
        """
        from hermes_android.runtime.env import prepare_runtime_env

        runtime = prepare_runtime_env(
            self.files_dir,
            api_server_port=self.api_server_port,
            api_server_key=self.api_server_key,
            api_server_model_name=self.api_server_model_name,
        )

        self._runtime_info = RuntimeInfo(
            files_dir=self.files_dir,
            hermes_home=runtime.hermes_home,
            api_server_host=runtime.api_server_host,
            api_server_port=runtime.api_server_port,
            api_server_key=runtime.api_server_key,
            api_server_model_name=runtime.api_server_model_name,
            base_url=f"http://127.0.0.1:{runtime.api_server_port}",
            probe_result=f"native-android-chaquopy; linux={getattr(self, '_linux_execution_mode', 'embedded')}",
            linux_execution_mode=getattr(self, '_linux_execution_mode', 'embedded'),
        )

    def _phase_ready(self) -> None:
        """Phase 9: Final ready phase."""
        # Mirror any Kotlin-verified local models into provider profiles so
        # the agent loop can route to on-device backends immediately. Never
        # fatal: an unreadable catalog just means no on-device providers yet.
        try:
            from hermes_android.providers.android_local import sync_android_local_catalog

            sync_android_local_catalog()
        except Exception as exc:  # noqa: BLE001
            logging.getLogger(__name__).warning(
                "android_local catalog sync skipped: %s", exc,
            )
        # Register the Kotlin-backed device facade so agent tool calls reach
        # Android capabilities over the single dispatch bridge (no-op on
        # desktop/test interpreters).
        try:
            from hermes_android.device.kotlin_facade import try_register_kotlin_facade

            try_register_kotlin_facade()
        except Exception as exc:  # noqa: BLE001
            logging.getLogger(__name__).warning(
                "device facade registration skipped: %s", exc,
            )
        # Start the Linux subsystem health monitor (30 s tick; persists
        # transitions so /v1/manage/linux/health reflects live flips).
        try:
            from hermes_android.linux.monitor import start_health_monitor

            start_health_monitor()
        except Exception as exc:  # noqa: BLE001
            logging.getLogger(__name__).warning(
                "linux health monitor skipped: %s", exc,
            )


def bootstrap_android_runtime(
    files_dir: str,
    *,
    api_server_port: int | None = None,
    api_server_key: str | None = None,
) -> dict[str, Any]:
    """Prepare the Android runtime without binding any sockets.

    Convenience entry used by :func:`hermes_android.runtime.server.start_local_api_server`
    and tests. Runs the preparation phases (profile, interpreter, config, assets,
    linux, mcp, memory) but never starts the API server.
    """
    global _last_orchestrator
    orchestrator = BootstrapOrchestrator(
        files_dir,
        api_server_port=api_server_port,
        api_server_key=api_server_key,
    )
    _last_orchestrator = orchestrator
    orchestrator.run_preparation_phases()

    from hermes_android.assets.bundled import configure_skill_env
    from hermes_android.linux.env import load_linux_subsystem_state

    info = orchestrator.runtime_info
    return {
        "runtime": {
            "files_dir": str(info.files_dir),
            "hermes_home": str(info.hermes_home),
            "api_server_host": info.api_server_host,
            "api_server_port": info.api_server_port,
            "api_server_key": info.api_server_key,
            "api_server_model_name": info.api_server_model_name,
        },
        "linux_subsystem": load_linux_subsystem_state(files_dir),
        "skill_env": configure_skill_env(),
        "phase_timings": dict(orchestrator.phase_timings),
    }