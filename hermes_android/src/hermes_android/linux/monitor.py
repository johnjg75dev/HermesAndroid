"""Process-wide Linux subsystem health monitor (P2 / M21).

Starts a :class:`LinuxHealthMonitor` around the active subsystem and persists
every health transition into the versioned state file, so
``GET /v1/manage/linux/health`` reflects live status within one 30 s tick —
including degraded flips when the subsystem process dies.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Optional

from hermes_android.linux.base import LinuxSubsystem
from hermes_android.linux.health import HealthEvent, LinuxHealthMonitor
from hermes_android.linux.state import LinuxStateManager

logger = logging.getLogger(__name__)

_monitor: Optional[LinuxHealthMonitor] = None
_subsystem: Optional[LinuxSubsystem] = None
_lock = threading.Lock()
_last_status: str = ""


def _on_health_event(event: HealthEvent) -> None:
    """Persist transitions so manage/linux/health reflects live flips.

    The state file is owned by Kotlin's HermesLinuxSubsystemBridge and carries
    many Kotlin-specific keys (runtime layout, artifact hashes, native tool
    paths). Health updates therefore MERGE into the raw JSON — never rewrite
    the file from the Python dataclass.
    """
    global _last_status
    status = event.status.value if hasattr(event.status, "value") else str(event.status)
    if status == _last_status:
        return
    previous = _last_status
    _last_status = status
    logger.info(
        "[linux-health] %s: %s -> %s", event.subsystem, previous or "unknown", status,
    )
    try:
        files_dir = _files_dir()
        if files_dir is None:
            return
        manager = LinuxStateManager(files_dir)
        raw = _load_raw_state(manager) or {}
        info = event.info
        updates = {
            "health": status,
            "last_probe_epoch_ms": int(time.time() * 1000),
            "execution_mode": event.subsystem,
            "shell_path": info.shell_path or raw.get("shell_path", ""),
            "bash_path": info.bash_path or raw.get("bash_path", ""),
            "prefix_path": info.prefix_path or raw.get("prefix_path", ""),
            "bin_path": info.bin_path or raw.get("bin_path", ""),
            "package_count": info.package_count or raw.get("package_count", 0),
            "version_string": info.version or raw.get("version_string", ""),
        }
        raw.update(updates)
        manager.save_raw(raw)
    except Exception as exc:  # noqa: BLE001 - persistence must not kill the tick
        logger.warning("[linux-health] could not persist state: %s", exc)


def _load_raw_state(manager: LinuxStateManager) -> Optional[dict]:
    try:
        import json

        path = getattr(manager, "_state_file", None)
        if path is not None and Path(path).is_file():
            return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    return None


def _files_dir() -> Optional[Path]:
    raw = ""
    try:
        import os

        raw = os.environ.get("HERMES_ANDROID_FILES_DIR", "")
    except Exception:
        raw = ""
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def start_health_monitor(interval_seconds: float = 30.0) -> bool:
    """Start monitoring the active subsystem; returns True when running.

    Idempotent: repeated calls while running are no-ops. Never raises — a
    missing/unavailable subsystem simply leaves the monitor stopped.
    """
    global _monitor, _subsystem, _last_status
    with _lock:
        if _monitor is not None:
            return True
        try:
            from hermes_android.linux.base import LinuxSubsystemFactory

            factory = LinuxSubsystemFactory(_files_dir())
            subsystem = factory.create_subsystem()
            initial = subsystem.probe()
            _subsystem = subsystem
            _last_status = initial.health.value
            # Seed persisted state so the first poll has real data — merge
            # into any Kotlin-owned file instead of replacing it.
            try:
                files_dir = _files_dir()
                if files_dir is not None:
                    manager = LinuxStateManager(files_dir)
                    raw = _load_raw_state(manager) or {}
                    raw.update({
                        "execution_mode": subsystem.execution_mode.value,
                        "enabled": True,
                        "health": initial.health.value,
                        "last_probe_epoch_ms": int(time.time() * 1000),
                        "shell_path": initial.shell_path,
                        "bash_path": initial.bash_path,
                        "prefix_path": initial.prefix_path,
                        "bin_path": initial.bin_path,
                        "home_path": initial.home_path,
                        "tmp_path": initial.tmp_path,
                        "native_library_dir": initial.native_library_dir,
                        "lib_path": initial.lib_path,
                        "version_string": initial.version,
                        "package_count": initial.package_count,
                        "termux_arch": initial.termux_arch,
                        "distro": str(raw.get("distro", "") or initial.version),
                    })
                    manager.save_raw(raw)
            except Exception as exc:  # noqa: BLE001
                logger.debug("[linux-health] seed save skipped: %s", exc)

            _monitor = LinuxHealthMonitor(
                subsystem,
                interval=interval_seconds,
                callback=_on_health_event,
            )
            _monitor.start()
            logger.info(
                "[linux-health] monitoring %s (%s) every %.0fs",
                subsystem.execution_mode.value,
                initial.health.value,
                interval_seconds,
            )
            return True
        except Exception as exc:  # noqa: BLE001 - unavailable is a normal state
            logger.info("[linux-health] monitor not started: %s", exc)
            _monitor = None
            _subsystem = None
            return False


def stop_health_monitor() -> None:
    """Stop the monitor if running (idempotent)."""
    global _monitor, _subsystem
    with _lock:
        if _monitor is not None:
            _monitor.stop()
        _monitor = None
        _subsystem = None


def health_monitor_running() -> bool:
    return _monitor is not None
