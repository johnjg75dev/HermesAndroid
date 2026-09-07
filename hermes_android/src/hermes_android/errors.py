"""Hermes Android error hierarchy with stable string codes.

Error codes are stable string identifiers that map 1:1 between Python and Kotlin.
Kotlin ErrorMapper must have exhaustive `when` branches for every code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class HermesErrorCode:
    """Stable error code with optional retry guidance."""

    code: str
    """Unique stable identifier (e.g., "PROFILE_NOT_FOUND", "FACADE_TIMEOUT")."""

    retryable: bool = False
    """Whether the operation can be retried without user intervention."""

    user_message: Optional[str] = None
    """Optional default user-facing message."""


# --- Error code registry (alphabetical) ---

# Bridge / API errors
UNSUPPORTED_BRIDGE_VERSION = HermesErrorCode(
    "UNSUPPORTED_BRIDGE_VERSION",
    retryable=False,
    user_message="Bridge version mismatch. Please update the Hermes app.",
)
BRIDGE_CONNECTION_FAILED = HermesErrorCode(
    "BRIDGE_CONNECTION_FAILED",
    retryable=True,
    user_message="Failed to connect to the Hermes runtime.",
)
BRIDGE_HANDSHAKE_FAILED = HermesErrorCode(
    "BRIDGE_HANDSHAKE_FAILED",
    retryable=False,
    user_message="Bridge handshake failed. Please restart the app.",
)

# Profile errors
PROFILE_NOT_FOUND = HermesErrorCode(
    "PROFILE_NOT_FOUND",
    retryable=False,
    user_message="The requested profile does not exist.",
)
PROFILE_SWITCH_FAILED = HermesErrorCode(
    "PROFILE_SWITCH_FAILED",
    retryable=False,
    user_message="Failed to switch profiles. Please try again.",
)
PROFILE_CORRUPTED = HermesErrorCode(
    "PROFILE_CORRUPTED",
    retryable=False,
    user_message="Profile data is corrupted. Please create a new profile.",
)

# Config errors
CONFIG_VALIDATION_FAILED = HermesErrorCode(
    "CONFIG_VALIDATION_FAILED",
    retryable=False,
    user_message="Configuration validation failed.",
)
CONFIG_MIGRATION_FAILED = HermesErrorCode(
    "CONFIG_MIGRATION_FAILED",
    retryable=False,
    user_message="Failed to migrate configuration.",
)

# Runtime errors
RUNTIME_NOT_STARTED = HermesErrorCode(
    "RUNTIME_NOT_STARTED",
    retryable=True,
    user_message="Hermes runtime is not started.",
)
RUNTIME_ALREADY_RUNNING = HermesErrorCode(
    "RUNTIME_ALREADY_RUNNING",
    retryable=False,
    user_message="Hermes runtime is already running.",
)
RUNTIME_START_FAILED = HermesErrorCode(
    "RUNTIME_START_FAILED",
    retryable=True,
    user_message="Failed to start Hermes runtime.",
)
RUNTIME_STOP_FAILED = HermesErrorCode(
    "RUNTIME_STOP_FAILED",
    retryable=True,
    user_message="Failed to stop Hermes runtime.",
)
RUNTIME_CRASHED = HermesErrorCode(
    "RUNTIME_CRASHED",
    retryable=True,
    user_message="Hermes runtime crashed. Restarting...",
)
BOOT_PHASE_FAILED = HermesErrorCode(
    "BOOT_PHASE_FAILED",
    retryable=False,
    user_message="Boot phase failed.",
)
BOOT_FATAL_PHASE_FAILED = HermesErrorCode(
    "BOOT_FATAL_PHASE_FAILED",
    retryable=False,
    user_message="Fatal boot phase failed. Cannot continue.",
)

# Device facade errors
DEVICE_UNAVAILABLE = HermesErrorCode(
    "DEVICE_UNAVAILABLE",
    retryable=True,
    user_message="Device capability is currently unavailable.",
)
PERMISSION_MISSING = HermesErrorCode(
    "PERMISSION_MISSING",
    retryable=False,
    user_message="Required Android permission is not granted.",
)
FACADE_TIMEOUT = HermesErrorCode(
    "FACADE_TIMEOUT",
    retryable=True,
    user_message="Device operation timed out.",
)
FACADE_CANCELLED = HermesErrorCode(
    "FACADE_CANCELLED",
    retryable=False,
    user_message="Device operation was cancelled.",
)
CONSENT_DENIED = HermesErrorCode(
    "CONSENT_DENIED",
    retryable=False,
    user_message="User denied consent for this operation.",
)

# Linux subsystem errors
LINUX_SUBSYSTEM_UNAVAILABLE = HermesErrorCode(
    "LINUX_SUBSYSTEM_UNAVAILABLE",
    retryable=True,
    user_message="Linux subsystem is not available.",
)
LINUX_SUBSYSTEM_DEGRADED = HermesErrorCode(
    "LINUX_SUBSYSTEM_DEGRADED",
    retryable=True,
    user_message="Linux subsystem is running in degraded mode.",
)
LINUX_PROOT_NOT_FOUND = HermesErrorCode(
    "LINUX_PROOT_NOT_FOUND",
    retryable=False,
    user_message="proot-distro not found. Cannot start Linux userland.",
)
LINUX_TERMUX_NOT_FOUND = HermesErrorCode(
    "LINUX_TERMUX_NOT_FOUND",
    retryable=False,
    user_message="Termux not found.",
)
LINUX_PACKAGE_INSTALL_FAILED = HermesErrorCode(
    "LINUX_PACKAGE_INSTALL_FAILED",
    retryable=True,
    user_message="Failed to install package in Linux subsystem.",
)

# Resource errors
RESOURCE_GAUGE_FAILED = HermesErrorCode(
    "RESOURCE_GAUGE_FAILED",
    retryable=True,
    user_message="Failed to read resource metrics.",
)
CLEANUP_FAILED = HermesErrorCode(
    "CLEANUP_FAILED",
    retryable=True,
    user_message="Resource cleanup partially failed.",
)

# Memory provider errors
MEMORY_PROVIDER_UNAVAILABLE = HermesErrorCode(
    "MEMORY_PROVIDER_UNAVAILABLE",
    retryable=True,
    user_message="Memory provider is not available.",
)
MEMORY_PROVIDER_SETUP_FAILED = HermesErrorCode(
    "MEMORY_PROVIDER_SETUP_FAILED",
    retryable=False,
    user_message="Failed to set up memory provider.",
)

# MCP errors
MCP_SERVER_NOT_FOUND = HermesErrorCode(
    "MCP_SERVER_NOT_FOUND",
    retryable=False,
    user_message="MCP server not found.",
)
MCP_SERVER_START_FAILED = HermesErrorCode(
    "MCP_SERVER_START_FAILED",
    retryable=True,
    user_message="Failed to start MCP server.",
)

# Session errors
SESSION_NOT_FOUND = HermesErrorCode(
    "SESSION_NOT_FOUND",
    retryable=False,
    user_message="Session not found.",
)
SESSION_DB_ERROR = HermesErrorCode(
    "SESSION_DB_ERROR",
    retryable=True,
    user_message="Session database error.",
)

# Generic / catch-all
INTERNAL_ERROR = HermesErrorCode(
    "INTERNAL_ERROR",
    retryable=True,
    user_message="An internal error occurred.",
)
UNKNOWN_ERROR = HermesErrorCode(
    "UNKNOWN_ERROR",
    retryable=False,
    user_message="An unknown error occurred.",
)


# --- Error code lookup ---

_ERROR_CODES: dict[str, HermesErrorCode] = {
    "UNSUPPORTED_BRIDGE_VERSION": UNSUPPORTED_BRIDGE_VERSION,
    "BRIDGE_CONNECTION_FAILED": BRIDGE_CONNECTION_FAILED,
    "BRIDGE_HANDSHAKE_FAILED": BRIDGE_HANDSHAKE_FAILED,
    "PROFILE_NOT_FOUND": PROFILE_NOT_FOUND,
    "PROFILE_SWITCH_FAILED": PROFILE_SWITCH_FAILED,
    "PROFILE_CORRUPTED": PROFILE_CORRUPTED,
    "CONFIG_VALIDATION_FAILED": CONFIG_VALIDATION_FAILED,
    "CONFIG_MIGRATION_FAILED": CONFIG_MIGRATION_FAILED,
    "RUNTIME_NOT_STARTED": RUNTIME_NOT_STARTED,
    "RUNTIME_ALREADY_RUNNING": RUNTIME_ALREADY_RUNNING,
    "RUNTIME_START_FAILED": RUNTIME_START_FAILED,
    "RUNTIME_STOP_FAILED": RUNTIME_STOP_FAILED,
    "RUNTIME_CRASHED": RUNTIME_CRASHED,
    "BOOT_PHASE_FAILED": BOOT_PHASE_FAILED,
    "BOOT_FATAL_PHASE_FAILED": BOOT_FATAL_PHASE_FAILED,
    "DEVICE_UNAVAILABLE": DEVICE_UNAVAILABLE,
    "PERMISSION_MISSING": PERMISSION_MISSING,
    "FACADE_TIMEOUT": FACADE_TIMEOUT,
    "FACADE_CANCELLED": FACADE_CANCELLED,
    "CONSENT_DENIED": CONSENT_DENIED,
    "LINUX_SUBSYSTEM_UNAVAILABLE": LINUX_SUBSYSTEM_UNAVAILABLE,
    "LINUX_SUBSYSTEM_DEGRADED": LINUX_SUBSYSTEM_DEGRADED,
    "LINUX_PROOT_NOT_FOUND": LINUX_PROOT_NOT_FOUND,
    "LINUX_TERMUX_NOT_FOUND": LINUX_TERMUX_NOT_FOUND,
    "LINUX_PACKAGE_INSTALL_FAILED": LINUX_PACKAGE_INSTALL_FAILED,
    "RESOURCE_GAUGE_FAILED": RESOURCE_GAUGE_FAILED,
    "CLEANUP_FAILED": CLEANUP_FAILED,
    "MEMORY_PROVIDER_UNAVAILABLE": MEMORY_PROVIDER_UNAVAILABLE,
    "MEMORY_PROVIDER_SETUP_FAILED": MEMORY_PROVIDER_SETUP_FAILED,
    "MCP_SERVER_NOT_FOUND": MCP_SERVER_NOT_FOUND,
    "MCP_SERVER_START_FAILED": MCP_SERVER_START_FAILED,
    "SESSION_NOT_FOUND": SESSION_NOT_FOUND,
    "SESSION_DB_ERROR": SESSION_DB_ERROR,
    "INTERNAL_ERROR": INTERNAL_ERROR,
    "UNKNOWN_ERROR": UNKNOWN_ERROR,
}


def get_error_code(code: str) -> HermesErrorCode:
    """Look up an error code by string identifier."""
    return _ERROR_CODES.get(code, UNKNOWN_ERROR)


def all_error_codes() -> list[HermesErrorCode]:
    """Return all registered error codes."""
    return list(_ERROR_CODES.values())


# --- Base exception hierarchy ---


class HermesError(Exception):
    """Base exception for all Hermes Android errors."""

    def __init__(
        self,
        code: HermesErrorCode | str,
        message: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
    ):
        if isinstance(code, HermesErrorCode):
            self.code = code.code
            self._code_obj = code
        else:
            self.code = code
            self._code_obj = get_error_code(code)
        self.message = message or self._code_obj.user_message or "Error"
        self.details = details or {}
        self.cause = cause
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict suitable for JSON transport."""
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self._code_obj.retryable,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HermesError":
        """Deserialize from a dict."""
        return cls(
            code=data["code"],
            message=data.get("message"),
            details=data.get("details"),
        )


class ProfileError(HermesError):
    """Profile-related errors."""

    def __init__(
        self,
        code: HermesErrorCode | str = PROFILE_NOT_FOUND,
        message: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
    ):
        super().__init__(code, message, details, cause)


class ConfigError(HermesError):
    """Configuration-related errors."""

    def __init__(
        self,
        code: HermesErrorCode | str = CONFIG_VALIDATION_FAILED,
        message: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
    ):
        super().__init__(code, message, details, cause)


class HermesRuntimeError(HermesError):
    """Runtime lifecycle errors."""

    def __init__(
        self,
        code: HermesErrorCode | str = RUNTIME_START_FAILED,
        message: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
    ):
        super().__init__(code, message, details, cause)


class BridgeError(HermesError):
    """Bridge/API communication errors."""

    def __init__(
        self,
        code: HermesErrorCode | str = BRIDGE_CONNECTION_FAILED,
        message: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
    ):
        super().__init__(code, message, details, cause)


class DeviceError(HermesError):
    """Device facade errors."""

    def __init__(
        self,
        code: HermesErrorCode | str = DEVICE_UNAVAILABLE,
        message: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
    ):
        super().__init__(code, message, details, cause)


class LinuxSubsystemError(HermesError):
    """Linux subsystem errors."""

    def __init__(
        self,
        code: HermesErrorCode | str = LINUX_SUBSYSTEM_UNAVAILABLE,
        message: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
    ):
        super().__init__(code, message, details, cause)


class ResourceError(HermesError):
    """Resource monitoring/cleanup errors."""

    def __init__(
        self,
        code: HermesErrorCode | str = RESOURCE_GAUGE_FAILED,
        message: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
    ):
        super().__init__(code, message, details, cause)


# --- Kotlin-facing error factory ---

def error_to_json(error: BaseException) -> str:
    """Convert any exception to a JSON string for Kotlin consumption."""
    if isinstance(error, HermesError):
        return error.to_dict().__str__().replace("'", '"')
    return HermesError(UNKNOWN_ERROR, str(error), cause=error).to_dict().__str__().replace("'", '"')