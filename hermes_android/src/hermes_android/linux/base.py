"""LinuxSubsystem ABC, HealthStatus, and errors for Android Linux subsystem."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any


class ExecutionMode(Enum):
    """Linux execution mode on Android."""

    EMBEDDED = "embedded"           # bundled busybox/native libs
    PROOT_DISTRO = "proot"          # proot-distro userland
    TERMUX = "termux"               # Termux enhancement


class HealthStatus(Enum):
    """Health status of the Linux subsystem."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SubsystemInfo:
    """Information about the Linux subsystem."""

    execution_mode: ExecutionMode
    health: HealthStatus
    shell_path: str
    bash_path: str
    prefix_path: str
    bin_path: str
    home_path: str
    tmp_path: str
    native_library_dir: str
    lib_path: str
    version: str
    package_count: int = 0
    termux_arch: str = ""


class LinuxSubsystemError(Exception):
    """Base exception for Linux subsystem errors."""

    def __init__(self, message: str, mode: ExecutionMode | None = None, cause: BaseException | None = None):
        self.mode = mode
        self.cause = cause
        super().__init__(message)


class LinuxSubsystem(ABC):
    """Abstract base class for Linux subsystem implementations."""

    @property
    @abstractmethod
    def execution_mode(self) -> ExecutionMode:
        """Return the execution mode."""
        pass

    @abstractmethod
    def probe(self) -> SubsystemInfo:
        """Probe the subsystem and return info. May raise on fatal errors."""
        pass

    @abstractmethod
    def get_shell_env(self) -> dict[str, str]:
        """Return environment variables for shell execution."""
        pass

    @abstractmethod
    def execute(self, command: str, timeout: int = 30) -> dict[str, Any]:
        """Execute a command in the subsystem."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the subsystem is available."""
        pass

    def health_check(self) -> HealthStatus:
        """Check subsystem health. Override for custom logic."""
        try:
            if not self.is_available():
                return HealthStatus.UNAVAILABLE
            info = self.probe()
            return info.health
        except Exception:
            return HealthStatus.DEGRADED


class LinuxSubsystemFactory:
    """Factory for creating the appropriate Linux subsystem."""

    def __init__(self, files_dir: Any):
        self.files_dir = files_dir

    def create_subsystem(self) -> LinuxSubsystem:
        """Create the best available subsystem based on what's installed."""
        # Try proot first
        from hermes_android.linux.proot import ProotSubsystem
        proot = ProotSubsystem(self.files_dir)
        if proot.is_available():
            return proot

        # Try Termux
        from hermes_android.linux.termux import TermuxSubsystem
        termux = TermuxSubsystem(self.files_dir)
        if termux.is_available():
            return termux

        # Fall back to embedded
        from hermes_android.linux.embedded import EmbeddedSubsystem
        return EmbeddedSubsystem(self.files_dir)