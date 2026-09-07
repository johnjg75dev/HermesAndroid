"""Termux optional enhancement path for Android Linux subsystem."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from hermes_android.linux.base import (
    ExecutionMode,
    HealthStatus,
    LinuxSubsystem,
    SubsystemInfo,
)


class TermuxSubsystem(LinuxSubsystem):
    """Termux-based Linux subsystem (optional enhancement)."""

    def __init__(self, files_dir: Path | str):
        self.files_dir = Path(files_dir).expanduser().resolve()
        self._hermes_home = self.files_dir / "hermes-home"
        self._linux_dir = self._hermes_home / "linux"
        self._termux_prefix: Path | None = None
        self._detect_termux()

    def _detect_termux(self) -> None:
        """Detect Termux installation."""
        # Common Termux locations
        candidates = [
            Path("/data/data/com.termux/files/usr"),
            Path.home() / "termux" / "usr",
            Path("/system/bin/termux"),
        ]
        for c in candidates:
            if c.exists() and (c / "bin" / "bash").exists():
                self._termux_prefix = c
                break

    @property
    def execution_mode(self) -> ExecutionMode:
        return ExecutionMode.TERMUX

    def probe(self) -> SubsystemInfo:
        """Probe Termux subsystem."""
        if not self._termux_prefix:
            return SubsystemInfo(
                execution_mode=self.execution_mode,
                health=HealthStatus.UNAVAILABLE,
                shell_path="",
                bash_path="",
                prefix_path="",
                bin_path="",
                home_path=str(self._linux_dir / "home"),
                tmp_path=str(self._linux_dir / "tmp"),
                native_library_dir="",
                lib_path="",
                version="termux",
                package_count=0,
                termux_arch="",
            )

        bash_path = str(self._termux_prefix / "bin" / "bash")

        # Get architecture
        arch = "unknown"
        try:
            result = subprocess.run(
                [bash_path, "-c", "uname -m"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            arch = result.stdout.strip() or "unknown"
        except Exception:
            pass

        # Count packages
        pkg_count = 0
        try:
            result = subprocess.run(
                [bash_path, "-c", "pkg list-installed 2>/dev/null | wc -l"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            pkg_count = int(result.stdout.strip()) if result.stdout.strip().isdigit() else 0
        except Exception:
            pass

        return SubsystemInfo(
            execution_mode=self.execution_mode,
            health=HealthStatus.HEALTHY,
            shell_path=bash_path,
            bash_path=bash_path,
            prefix_path=str(self._termux_prefix),
            bin_path=str(self._termux_prefix / "bin"),
            home_path=str(self._linux_dir / "home"),
            tmp_path=str(self._linux_dir / "tmp"),
            native_library_dir=str(self._termux_prefix / "lib"),
            lib_path=str(self._termux_prefix / "lib"),
            version=f"termux:{arch}",
            package_count=pkg_count,
            termux_arch=arch,
        )

    def get_shell_env(self) -> dict[str, str]:
        """Get environment for Termux shell execution."""
        if not self._termux_prefix:
            return {}

        lib_dir = str(self._termux_prefix / "lib")
        return {
            "TERMINAL_ENV": "android_linux",
            "HERMES_ANDROID_EXECUTION_MODE": "termux",
            "HERMES_ANDROID_SHELL": "/system/bin/sh",
            "HERMES_ANDROID_NATIVE_SHELL": str(self._termux_prefix / "bin" / "bash"),
            "HERMES_ANDROID_LINUX_PREFIX": str(self._termux_prefix),
            "HERMES_ANDROID_LINUX_BASH": str(self._termux_prefix / "bin" / "bash"),
            "HERMES_ANDROID_LINUX_NATIVE_BASH": str(self._termux_prefix / "bin" / "bash"),
            "HERMES_ANDROID_LINUX_BIN": str(self._termux_prefix / "bin"),
            "HERMES_ANDROID_LINUX_LIB": lib_dir,
            "HERMES_ANDROID_NATIVE_LIB": lib_dir,
            "HERMES_ANDROID_ALLOW_PREFIX_BIN": "1",
            "LD_LIBRARY_PATH": lib_dir,
            "HERMES_ANDROID_LINUX_HOME": str(self._linux_dir / "home"),
            "HERMES_ANDROID_LINUX_TMP": str(self._linux_dir / "tmp"),
            "HOME": str(self._linux_dir / "home"),
            "TMPDIR": str(self._linux_dir / "tmp"),
            "TERMINAL_CWD": str(self._linux_dir / "home"),
            "PATH": f"{self._termux_prefix}/bin:{self._termux_prefix}/bin/applets:/system/bin:/system/xbin",
            "TERMUX_ARCH": self._get_arch(),
        }

    def _get_arch(self) -> str:
        """Get Termux architecture."""
        try:
            result = subprocess.run(
                ["uname", "-m"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout.strip() or "unknown"
        except Exception:
            return "unknown"

    def execute(self, command: str, timeout: int = 30) -> dict[str, Any]:
        """Execute a command in Termux."""
        if not self._termux_prefix:
            return {
                "exit_code": 1,
                "stdout": "",
                "stderr": "Termux not found",
            }

        bash_path = str(self._termux_prefix / "bin" / "bash")
        env = self.get_shell_env()
        env.update(os.environ)

        try:
            result = subprocess.run(
                [bash_path, "-c", command],
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self._linux_dir / "home"),
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
        """Check if Termux is available."""
        return self._termux_prefix is not None

    # --- Package management ---

    def pkg_install(self, packages: list[str]) -> dict[str, Any]:
        """Install packages via pkg."""
        if not self._termux_prefix:
            return {"success": False, "error": "Termux not available"}

        bash_path = str(self._termux_prefix / "bin" / "bash")
        env = self.get_shell_env()
        env.update(os.environ)

        pkg_str = " ".join(packages)
        cmd = f"pkg install -y {pkg_str}"

        try:
            result = subprocess.run(
                [bash_path, "-c", cmd],
                env=env,
                capture_output=True,
                text=True,
                timeout=300,
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def pkg_remove(self, packages: list[str]) -> dict[str, Any]:
        """Remove packages via pkg."""
        if not self._termux_prefix:
            return {"success": False, "error": "Termux not available"}

        bash_path = str(self._termux_prefix / "bin" / "bash")
        env = self.get_shell_env()
        env.update(os.environ)

        pkg_str = " ".join(packages)
        cmd = f"pkg remove -y {pkg_str}"

        try:
            result = subprocess.run(
                [bash_path, "-c", cmd],
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def pkg_list(self) -> dict[str, Any]:
        """List installed packages."""
        if not self._termux_prefix:
            return {"packages": []}

        bash_path = str(self._termux_prefix / "bin" / "bash")
        env = self.get_shell_env()
        env.update(os.environ)

        try:
            result = subprocess.run(
                [bash_path, "-c", "pkg list-installed"],
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            packages = []
            for line in result.stdout.split("\n"):
                if "/" in line:
                    parts = line.split("/")
                    if len(parts) >= 2:
                        packages.append(parts[0])
            return {"packages": packages}
        except Exception as e:
            return {"success": False, "error": str(e)}