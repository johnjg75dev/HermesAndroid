"""proot-distro userland management for Android Linux subsystem."""

from __future__ import annotations

import json
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


class ProotSubsystem(LinuxSubsystem):
    """proot-distro based Linux subsystem."""

    def __init__(self, files_dir: Path | str):
        self.files_dir = Path(files_dir).expanduser().resolve()
        self._hermes_home = self.files_dir / "hermes-home"
        self._linux_dir = self._hermes_home / "linux"
        self._proot_dir = self._linux_dir / "proot-distro"
        self._installed_dists_dir = self._proot_dir / "installed-rootfs"
        self._state_file = self._linux_dir / "proot-state.json"

        # Ensure directories exist
        for d in [self._proot_dir, self._installed_dists_dir, self._linux_dir / "home", self._linux_dir / "tmp"]:
            d.mkdir(parents=True, exist_ok=True)

        self._current_distro: str | None = None
        self._load_state()

    def _load_state(self) -> None:
        """Load persisted state."""
        if self._state_file.exists():
            try:
                with open(self._state_file) as f:
                    state = json.load(f)
                    self._current_distro = state.get("current_distro")
            except Exception:
                pass

    def _save_state(self) -> None:
        """Persist state."""
        try:
            with open(self._state_file, "w") as f:
                json.dump({"current_distro": self._current_distro}, f)
        except Exception:
            pass

    @property
    def execution_mode(self) -> ExecutionMode:
        return ExecutionMode.PROOT_DISTRO

    def probe(self) -> SubsystemInfo:
        """Probe proot-distro subsystem."""
        # Check if proot is available
        proot_bin = self._find_proot_binary()
        if not proot_bin:
            return SubsystemInfo(
                execution_mode=self.execution_mode,
                health=HealthStatus.UNAVAILABLE,
                shell_path="",
                bash_path="",
                prefix_path=str(self._linux_dir),
                bin_path=str(self._proot_dir / "bin"),
                home_path=str(self._linux_dir / "home"),
                tmp_path=str(self._linux_dir / "tmp"),
                native_library_dir="",
                lib_path="",
                version="proot-distro",
                package_count=0,
            )

        # Check if a distro is installed
        if not self._current_distro:
            return SubsystemInfo(
                execution_mode=self.execution_mode,
                health=HealthStatus.DEGRADED,
                shell_path="",
                bash_path="",
                prefix_path=str(self._linux_dir),
                bin_path=str(self._proot_dir / "bin"),
                home_path=str(self._linux_dir / "home"),
                tmp_path=str(self._linux_dir / "tmp"),
                native_library_dir="",
                lib_path="",
                version="proot-distro",
                package_count=0,
            )

        distro_root = self._installed_dists_dir / self._current_distro
        bash_path = str(distro_root / "bin" / "bash")

        return SubsystemInfo(
            execution_mode=self.execution_mode,
            health=HealthStatus.HEALTHY,
            shell_path=bash_path,
            bash_path=bash_path,
            prefix_path=str(distro_root),
            bin_path=str(distro_root / "bin"),
            home_path=str(self._linux_dir / "home"),
            tmp_path=str(self._linux_dir / "tmp"),
            native_library_dir=str(distro_root / "lib"),
            lib_path=str(distro_root / "lib"),
            version=f"proot-distro:{self._current_distro}",
            package_count=self._count_packages(distro_root),
        )

    def _find_proot_binary(self) -> Path | None:
        """Find the proot binary."""
        candidates = [
            self._proot_dir / "bin" / "proot",
            Path("/data/local/tmp/proot"),
            Path("/system/bin/proot"),
        ]
        for c in candidates:
            if c.exists() and os.access(c, os.X_OK):
                return c
        return None

    def _count_packages(self, distro_root: Path) -> int:
        """Count installed packages in the distro."""
        try:
            dpkg = distro_root / "usr" / "bin" / "dpkg-query"
            if dpkg.exists():
                result = subprocess.run(
                    [str(dpkg), "-l"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                return len([l for l in result.stdout.split("\n") if l.startswith("ii")])
        except Exception:
            pass
        return 0

    def get_shell_env(self) -> dict[str, str]:
        """Get environment for proot shell execution."""
        if not self._current_distro:
            return {}

        distro_root = self._installed_dists_dir / self._current_distro
        lib_dirs = [
            str(distro_root / "lib"),
            str(distro_root / "usr" / "lib"),
            str(distro_root / "lib64"),
        ]
        ld_library_path = ":".join(lib_dirs)

        return {
            "TERMINAL_ENV": "android_linux",
            "HERMES_ANDROID_EXECUTION_MODE": "proot",
            "HERMES_ANDROID_SHELL": "/system/bin/sh",
            "HERMES_ANDROID_NATIVE_SHELL": str(distro_root / "bin" / "bash"),
            "HERMES_ANDROID_LINUX_PREFIX": str(distro_root),
            "HERMES_ANDROID_LINUX_BASH": str(distro_root / "bin" / "bash"),
            "HERMES_ANDROID_LINUX_NATIVE_BASH": str(distro_root / "bin" / "bash"),
            "HERMES_ANDROID_LINUX_BIN": str(distro_root / "bin"),
            "HERMES_ANDROID_LINUX_LIB": str(distro_root / "lib"),
            "HERMES_ANDROID_NATIVE_LIB": str(distro_root / "lib"),
            "HERMES_ANDROID_ALLOW_PREFIX_BIN": "1",
            "LD_LIBRARY_PATH": ld_library_path,
            "HERMES_ANDROID_LINUX_HOME": str(self._linux_dir / "home"),
            "HERMES_ANDROID_LINUX_TMP": str(self._linux_dir / "tmp"),
            "HOME": str(self._linux_dir / "home"),
            "TMPDIR": str(self._linux_dir / "tmp"),
            "TERMINAL_CWD": str(self._linux_dir / "home"),
            "PATH": f"{distro_root}/bin:{distro_root}/usr/bin:/system/bin:/system/xbin",
            "PROOT_DISTRO": self._current_distro,
        }

    def execute(self, command: str, timeout: int = 30) -> dict[str, Any]:
        """Execute a command in proot-distro."""
        if not self._current_distro:
            return {
                "exit_code": 1,
                "stdout": "",
                "stderr": "No proot-distro installed. Run 'install' action first.",
            }

        proot_bin = self._find_proot_binary()
        if not proot_bin:
            return {
                "exit_code": 1,
                "stdout": "",
                "stderr": "proot binary not found",
            }

        distro_root = self._installed_dists_dir / self._current_distro
        env = self.get_shell_env()
        env.update(os.environ)

        # Build proot command
        proot_cmd = [
            str(proot_bin),
            "--link2symlink",
            "-0",
            "-r", str(distro_root),
            "-b", f"{self._linux_dir}/home:/root",
            "-b", f"{self._linux_dir}/tmp:/tmp",
            "-w", "/root",
            "/bin/bash", "-c", command,
        ]

        try:
            result = subprocess.run(
                proot_cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
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
        """Check if proot-distro is available."""
        return self._find_proot_binary() is not None

    # --- Distro management ---

    def install_distro(self, distro: str = "ubuntu-24.04") -> dict[str, Any]:
        """Install a proot-distro."""
        # This would use the proot-distro script to install
        # For now, return a placeholder
        return {
            "success": False,
            "error": "proot-distro install not yet implemented in embedded Python",
        }

    def remove_distro(self, distro: str) -> dict[str, Any]:
        """Remove a proot-distro."""
        return {
            "success": False,
            "error": "proot-distro remove not yet implemented",
        }

    def list_distros(self) -> dict[str, Any]:
        """List installed distros."""
        distros = []
        if self._installed_dists_dir.exists():
            for d in self._installed_dists_dir.iterdir():
                if d.is_dir():
                    distros.append(d.name)
        return {
            "installed": distros,
            "current": self._current_distro,
        }

    def set_current_distro(self, distro: str) -> dict[str, Any]:
        """Set the current active distro."""
        distro_path = self._installed_dists_dir / distro
        if not distro_path.exists():
            return {"success": False, "error": f"Distro {distro} not installed"}
        self._current_distro = distro
        self._save_state()
        return {"success": True}