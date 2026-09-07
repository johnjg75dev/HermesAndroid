"""API app — wires APIServerAdapter + mounts the manage channel.

The manage channel shares the agent's aiohttp app via the generic
``extra_route_registrar`` hook in ``PlatformConfig.extra`` (see
``gateway/platforms/api_server.py``). ``mount_manage_routes`` is passed as
the registrar by both runtime start paths.
"""

from __future__ import annotations

from typing import Any

from hermes_android.api.manage import mount_manage_routes


def extra_route_registrar() -> Any:
    """Registrar callable handed to APIServerAdapter via config extra."""
    return mount_manage_routes


# Back-compat for earlier skeleton callers (kept importable, no behavior).
class APIApp:
    def __init__(self, runtime_handle: Any = None):
        self.runtime_handle = runtime_handle


def create_api_app(runtime_handle: Any = None) -> APIApp:
    return APIApp(runtime_handle)
