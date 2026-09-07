"""Versioned state.json schema for Linux subsystem."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from hermes_android.linux.base import ExecutionMode, HealthStatus, SubsystemInfo


STATE_VERSION = 1


@dataclass
class LinuxSubsystemState:
    """Versioned state for Linux subsystem."""

    version: int = STATE_VERSION
    execution_mode: str = ExecutionMode.EMBEDDED.value
    enabled: bool = False
    shell_path: str = ""
    bash_path: str = ""
    prefix_path: str = ""
    bin_path: str = ""
    home_path: str = ""
    tmp_path: str = ""
    native_library_dir: str = ""
    lib_path: str = ""
    version_string: str = ""
    package_count: int = 0
    termux_arch: str = ""
    health: str = HealthStatus.UNKNOWN.value
    last_probe_epoch_ms: int = 0
    distro: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_subsystem_info(cls, info: SubsystemInfo, enabled: bool = True) -> "LinuxSubsystemState":
        """Create state from SubsystemInfo."""
        return cls(
            execution_mode=info.execution_mode.value,
            enabled=enabled,
            shell_path=info.shell_path,
            bash_path=info.bash_path,
            prefix_path=info.prefix_path,
            bin_path=info.bin_path,
            home_path=info.home_path,
            tmp_path=info.tmp_path,
            native_library_dir=info.native_library_dir,
            lib_path=info.lib_path,
            version_string=info.version,
            package_count=info.package_count,
            termux_arch=info.termux_arch,
            health=info.health.value,
        )

    def to_subsystem_info(self) -> SubsystemInfo:
        """Convert back to SubsystemInfo."""
        return SubsystemInfo(
            execution_mode=ExecutionMode(self.execution_mode),
            health=HealthStatus(self.health),
            shell_path=self.shell_path,
            bash_path=self.bash_path,
            prefix_path=self.prefix_path,
            bin_path=self.bin_path,
            home_path=self.home_path,
            tmp_path=self.tmp_path,
            native_library_dir=self.native_library_dir,
            lib_path=self.lib_path,
            version=self.version_string,
            package_count=self.package_count,
            termux_arch=self.termux_arch,
        )


class LinuxStateManager:
    """Manages persisted Linux subsystem state."""

    def __init__(self, files_dir: Path | str):
        self.files_dir = Path(files_dir).expanduser().resolve()
        self._state_file = self.files_dir / "hermes-home" / "linux" / "linux-subsystem-state.json"
        self._state_file.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> LinuxSubsystemState | None:
        """Load state from file."""
        if not self._state_file.exists():
            return None
        try:
            with open(self._state_file) as f:
                data = json.load(f)
            # Handle version migration
            if data.get("version", 0) < STATE_VERSION:
                data = self._migrate(data)
            return LinuxSubsystemState(**data)
        except Exception:
            return None

    def save(self, state: LinuxSubsystemState) -> None:
        """Save state to file."""
        state.version = STATE_VERSION
        with open(self._state_file, "w") as f:
            json.dump(asdict(state), f, indent=2)

    def save_raw(self, data: dict[str, Any]) -> None:
        """Merge-save raw dict without dropping unknown (Kotlin-owned) keys."""
        data["version"] = STATE_VERSION
        with open(self._state_file, "w") as f:
            json.dump(data, f, indent=2)

    def _migrate(self, data: dict[str, Any]) -> dict[str, Any]:
        """Migrate old state format to current version."""
        # Add defaults for new fields
        defaults = {
            "version": STATE_VERSION,
            "execution_mode": ExecutionMode.EMBEDDED.value,
            "enabled": False,
            "shell_path": "",
            "bash_path": "",
            "prefix_path": "",
            "bin_path": "",
            "home_path": "",
            "tmp_path": "",
            "native_library_dir": "",
            "lib_path": "",
            "version_string": "",
            "package_count": 0,
            "termux_arch": "",
            "health": HealthStatus.UNKNOWN.value,
            "last_probe_epoch_ms": 0,
            "distro": "",
            "extra": {},
        }
        for key, default in defaults.items():
            if key not in data:
                data[key] = default
        return data

    def clear(self) -> None:
        """Clear state file."""
        if self._state_file.exists():
            self._state_file.unlink()