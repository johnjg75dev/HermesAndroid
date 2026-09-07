"""API versioning and bridge_version handshake."""

from __future__ import annotations

from dataclasses import dataclass


# Bridge version - increment when wire protocol changes
BRIDGE_VERSION = 1

# Minimum supported bridge version
MIN_BRIDGE_VERSION = 1


@dataclass(frozen=True)
class BridgeVersionInfo:
    """Bridge version information."""

    version: int
    min_version: int
    features: list[str]


def get_bridge_version_info() -> BridgeVersionInfo:
    """Get bridge version info for handshake."""
    return BridgeVersionInfo(
        version=BRIDGE_VERSION,
        min_version=MIN_BRIDGE_VERSION,
        features=[
            "manage_api",
            "sse_events",
            "approval",
            "clarify",
            "moa_events",
            "delegate_attribution",
            "device_progress",
            "steer_queue",
        ],
    )


def check_bridge_version(client_version: int) -> tuple[bool, str | None]:
    """Check if client bridge version is compatible.

    Returns (compatible, error_message).
    """
    if client_version < MIN_BRIDGE_VERSION:
        return False, f"UNSUPPORTED_BRIDGE_VERSION: client {client_version} < min {MIN_BRIDGE_VERSION}"
    if client_version > BRIDGE_VERSION:
        return False, f"UNSUPPORTED_BRIDGE_VERSION: client {client_version} > server {BRIDGE_VERSION}"
    return True, None


UNSUPPORTED_BRIDGE = "UNSUPPORTED_BRIDGE_VERSION"