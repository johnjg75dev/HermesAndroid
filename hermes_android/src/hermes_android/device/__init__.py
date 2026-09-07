"""Device module exports."""

from hermes_android.device.facade import (
    DeviceFacade,
    FacadeResult,
    STUB_FACADE,
)
from hermes_android.device.registry import (
    FacadeRegistry,
    get_facade,
    register_facade,
    get_capability_snapshot,
)

__all__ = [
    "DeviceFacade",
    "FacadeResult",
    "STUB_FACADE",
    "FacadeRegistry",
    "get_facade",
    "register_facade",
    "get_capability_snapshot",
]