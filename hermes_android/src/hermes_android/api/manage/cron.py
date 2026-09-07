"""Cron management routes — thin CRUD over cron.jobs."""

from __future__ import annotations

import json
from typing import Any

from aiohttp import web

from hermes_android.api.manage import error_response, json_response


def register_routes(web_app: web.Application) -> None:
    async def list_jobs(request: web.Request) -> web.Response:
        from cron import jobs as cron_jobs

        include_disabled = request.query.get("include_disabled", "1") in {"1", "true"}
        return json_response({"jobs": cron_jobs.list_jobs(include_disabled=include_disabled)})

    async def create_job(request: web.Request) -> web.Response:
        from cron import jobs as cron_jobs

        try:
            body = await request.json()
        except Exception:
            return error_response("Invalid JSON body", "INVALID_ARGUMENT", 400)
        prompt = str(body.get("prompt", "") or "").strip()
        schedule = str(body.get("schedule", "") or "").strip()
        if not prompt or not schedule:
            return error_response("Both 'prompt' and 'schedule' are required", "INVALID_ARGUMENT", 400)
        try:
            job = cron_jobs.create_job(
                prompt=prompt,
                schedule=schedule,
                name=body.get("name"),
                repeat=body.get("repeat"),
                deliver=body.get("deliver"),
                skills=body.get("skills"),
                model=body.get("model"),
                provider=body.get("provider"),
                base_url=body.get("base_url") or None,
            )
        except Exception as exc:
            return error_response(f"Invalid job: {exc}", "CRON_INVALID_JOB", 400)
        return json_response({"job": _safe(job)}, status=201)

    async def get_job(request: web.Request) -> web.Response:
        from cron import jobs as cron_jobs

        ref = request.match_info["job_ref"]
        try:
            resolved = cron_jobs.resolve_job_ref(ref)
        except Exception:
            resolved = None
        if isinstance(resolved, dict):
            candidates = [resolved.get("id")]
        else:
            candidates = [ref]
        for job_id in candidates:
            job = cron_jobs.get_job(job_id) if job_id else None
            if job:
                return json_response({"job": _safe(job)})
        return error_response(f"Job not found: {ref}", "CRON_JOB_NOT_FOUND", 404)

    async def patch_job(request: web.Request) -> web.Response:
        from cron import jobs as cron_jobs

        try:
            body = await request.json()
        except Exception:
            return error_response("Invalid JSON body", "INVALID_ARGUMENT", 400)
        job_id = request.match_info["job_id"]
        updates = {k: v for k, v in body.items() if k in {
            "name", "prompt", "schedule", "model", "provider", "deliver",
            "skills", "repeat",
        }}
        updated = cron_jobs.update_job(job_id, updates)
        if not updated:
            return error_response(f"Job not found: {job_id}", "CRON_JOB_NOT_FOUND", 404)
        return json_response({"job": _safe(updated)})

    async def pause_job(request: web.Request) -> web.Response:
        from cron import jobs as cron_jobs

        job_id = request.match_info["job_id"]
        paused = cron_jobs.pause_job(job_id)
        if not paused:
            return error_response(f"Job not found: {job_id}", "CRON_JOB_NOT_FOUND", 404)
        return json_response({"job": _safe(paused), "action": "paused"})

    async def resume_job(request: web.Request) -> web.Response:
        from cron import jobs as cron_jobs

        job_id = request.match_info["job_id"]
        resumed = cron_jobs.resume_job(job_id)
        if not resumed:
            return error_response(f"Job not found: {job_id}", "CRON_JOB_NOT_FOUND", 404)
        return json_response({"job": _safe(resumed), "action": "resumed"})

    async def remove_job(request: web.Request) -> web.Response:
        from cron import jobs as cron_jobs

        job_id = request.match_info["job_id"]
        removed = cron_jobs.remove_job(job_id)
        if not removed:
            return error_response(f"Job not found: {job_id}", "CRON_JOB_NOT_FOUND", 404)
        return json_response({"removed": True, "job_id": job_id})

    web_app.router.add_get("/v1/manage/cron/{job_ref}", get_job)
    web_app.router.add_post("/v1/manage/cron", create_job)
    web_app.router.add_patch("/v1/manage/cron/{job_id}", patch_job)
    web_app.router.add_post("/v1/manage/cron/{job_id}/pause", pause_job)
    web_app.router.add_post("/v1/manage/cron/{job_id}/resume", resume_job)
    web_app.router.add_delete("/v1/manage/cron/{job_id}", remove_job)
    web_app.router.add_get("/v1/manage/cron", list_jobs)


def _safe(job: Any) -> Any:
    """Cron job records may be dicts or objects; normalize to plain JSON."""
    if isinstance(job, dict):
        return json.loads(json.dumps(job, default=str))
    return {"repr": str(job)}
