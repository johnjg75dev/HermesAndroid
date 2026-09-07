"""Embedded Linux subsystem (default): bundled busybox/native libs, no Termux."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from hermes_android.linux.base import (
    ExecutionMode,
    HealthStatus,
    LinuxSubsystem,
    LinuxSubsystemError,
    SubsystemInfo,
)


class EmbeddedSubsystem(LinuxSubsystem):
    """Embedded Linux subsystem using bundled binaries."""

    def __init__(self, files_dir: Path | str):
        self.files_dir = Path(files_dir).expanduser().resolve()
        self._hermes_home = self.files_dir / "hermes-home"
        self._linux_dir = self._hermes_home / "linux"
        self._bin_dir = self._linux_dir / "bin"
        self._lib_dir = self._linux_dir / "lib"
        self._home_dir = self._linux_dir / "home"
        self._tmp_dir = self._linux_dir / "tmp"

        # Ensure directories exist
        for d in [self._bin_dir, self._lib_dir, self._home_dir, self._tmp_dir]:
            d.mkdir(parents=True, exist_ok=True)

    @property
    def execution_mode(self) -> ExecutionMode:
        return ExecutionMode.EMBEDDED

    def probe(self) -> SubsystemInfo:
        """Probe the embedded subsystem."""
        shell_path = str(self._bin_dir / "sh")
        bash_path = str(self._bin_dir / "bash")

        # Check if busybox exists
        busybox_path = self._bin_dir / "busybox"
        if not busybox_path.exists():
            # This is expected on first run - assets are synced later
            return SubsystemInfo(
                execution_mode=self.execution_mode,
                health=HealthStatus.DEGRADED,
                shell_path=shell_path,
                bash_path=bash_path,
                prefix_path=str(self._linux_dir),
                bin_path=str(self._bin_dir),
                home_path=str(self._home_dir),
                tmp_path=str(self._tmp_dir),
                native_library_dir=str(self._lib_dir),
                lib_path=str(self._lib_dir),
                version="embedded",
                package_count=0,
            )

        # Try to get version
        version = "unknown"
        try:
            result = subprocess.run(
                [str(busybox_path), "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            version = result.stdout.strip().split("\n")[0] if result.stdout else "busybox"
        except Exception:
            pass

        return SubsystemInfo(
            execution_mode=self.execution_mode,
            health=HealthStatus.HEALTHY,
            shell_path=shell_path,
            bash_path=bash_path,
            prefix_path=str(self._linux_dir),
            bin_path=str(self._bin_dir),
            home_path=str(self._home_dir),
            tmp_path=str(self._tmp_dir),
            native_library_dir=str(self._lib_dir),
            lib_path=str(self._lib_dir),
            version=version,
            package_count=0,
        )

    def get_shell_env(self) -> dict[str, str]:
        """Get environment for shell execution."""
        return {
            "TERMINAL_ENV": "android_linux",
            "HERMES_ANDROID_EXECUTION_MODE": "embedded",
            "HERMES_ANDROID_SHELL": "/system/bin/sh",
            "HERMES_ANDROID_NATIVE_SHELL": str(self._bin_dir / "bash"),
            "HERMES_ANDROID_LINUX_PREFIX": str(self._linux_dir),
            "HERMES_ANDROID_LINUX_BASH": str(self._bin_dir / "bash"),
            "HERMES_ANDROID_LINUX_NATIVE_BASH": str(self._bin_dir / "bash"),
            "HERMES_ANDROID_LINUX_BIN": str(self._bin_dir),
            "HERMES_ANDROID_LINUX_LIB": str(self._lib_dir),
            "HERMES_ANDROID_NATIVE_LIB": str(self._lib_dir),
            "HERMES_ANDROID_ALLOW_PREFIX_BIN": "0",
            "LD_LIBRARY_PATH": str(self._lib_dir),
            "HERMES_ANDROID_LINUX_HOME": str(self._home_dir),
            "HERMES_ANDROID_LINUX_TMP": str(self._tmp_dir),
            "HOME": str(self._home_dir),
            "TMPDIR": str(self._tmp_dir),
            "TERMINAL_CWD": str(self._home_dir),
            "PATH": f"{self._bin_dir}:/system/bin:/system/xbin",
        }

    def execute(self, command: str, timeout: int = 30) -> dict[str, Any]:
        """Execute a command using the embedded shell."""
        env = self.get_shell_env()
        env.update(os.environ)

        try:
            result = subprocess.run(
                ["sh", "-c", command],
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self._home_dir),
            )
            return {
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except subprocess.TimeoutExpired:
            return {
                "exit_code": 124,
                "stdout": "",
                "stderr": f"Command timed out after {timeout}s",
            }
        except Exception as e:
            return {
                "exit_code": 1,
                "stdout": "",
                "stderr": str(e),
            }

    def is_available(self) -> bool:
        """Embedded is always available (may be degraded)."""
        return True