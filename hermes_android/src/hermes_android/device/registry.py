"""Device facade registry - registers Kotlin proxy implementations."""

from __future__ import annotations

from typing import Any

from hermes_android.device.facade import DeviceFacade, FacadeResult, STUB_FACADE


class FacadeRegistry:
    """Registry for the active device facade implementation."""

    _instance: "FacadeRegistry | None" = None
    _facade: DeviceFacade = STUB_FACADE

    def __new__(cls) -> "FacadeRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def register_facade(self, facade: DeviceFacade) -> None:
        """Register the Kotlin-provided facade implementation."""
        self._facade = facade

    def get_facade(self) -> DeviceFacade:
        """Get the current facade implementation."""
        return self._facade

    def reset(self) -> None:
        """Reset to stub (for testing)."""
        self._facade = STUB_FACADE


# Convenience function for Python code
def get_facade() -> DeviceFacade:
    """Get the current device facade."""
    return FacadeRegistry().get_facade()


def register_facade(facade: DeviceFacade) -> None:
    """Register a facade implementation."""
    FacadeRegistry().register_facade(facade)


# --- Capability snapshot ---

def get_capability_snapshot() -> dict[str, Any]:
    """Get a fresh capability snapshot from the registered facade.

    This replaces the stale capability snapshots in the old device_bridge.py.
    """
    facade = get_facade()
    try:
        result = facade.system_info()
        if result.success and isinstance(result.data, dict):
            return result.data
    except Exception:
        pass
    return {"error": "Facade not available", "mode": "stub"}