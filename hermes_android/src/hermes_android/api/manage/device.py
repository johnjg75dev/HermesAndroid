"""Device management routes — fresh capability snapshot from the device proxy."""

from __future__ import annotations

from aiohttp import web

from hermes_android.api.manage import json_response


def register_routes(web_app: web.Application) -> None:
    async def device_status(request: web.Request) -> web.Response:
        try:
            from hermes_android.device.proxy import read_device_capabilities

            return json_response({"capabilities": read_device_capabilities()})
        except ImportError:
            return json_response({
                "capabilities": {},
                "note": "device proxy unavailable outside the Android runtime",
            })

    web_app.router.add_get("/v1/manage/device", device_status)
