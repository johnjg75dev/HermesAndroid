"""Migration management routes — one-shot legacy data import.

GET  /v1/manage/migration            → status (done? marker?)
POST /v1/manage/migration            → run the import; body carries the raw
                                        ConversationStore JSON payload
"""

from __future__ import annotations

from aiohttp import web

from hermes_android.api.manage import error_response, json_response


def register_routes(web_app: web.Application) -> None:
    async def status(request: web.Request) -> web.Response:
        from hermes_android.migration.legacy import migration_status

        return json_response(migration_status())

    async def run_migration(request: web.Request) -> web.Response:
        from hermes_android.migration.legacy import import_legacy_conversations

        try:
            body = await request.json()
        except Exception:
            return error_response("Invalid JSON body", "INVALID_ARGUMENT", 400)
        payload = body.get("payload")
        if payload is None and isinstance(body.get("conversations"), list):
            # Accept the store array directly.
            import json as _json

            payload = _json.dumps(body["conversations"])
        if not payload:
            return error_response(
                "Missing legacy conversation 'payload'",
                "INVALID_ARGUMENT",
                400,
            )

        try:
            summary = import_legacy_conversations(str(payload))
        except ValueError as exc:
            return error_response(str(exc), "MIGRATION_INVALID_PAYLOAD", 400)
        except Exception as exc:  # noqa: BLE001 - surface typed failure card
            return error_response(f"Migration failed and was rolled back: {exc}", "MIGRATION_FAILED", 500)
        return json_response(summary)

    web_app.router.add_get("/v1/manage/migration", status)
    web_app.router.add_post("/v1/manage/migration", run_migration)
