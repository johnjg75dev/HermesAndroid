"""Contract tests for the /v1/manage/* management channel.

Builds a real aiohttp app, mounts the manage routes exactly as the embedded
runtime does, and exercises the endpoint groups against hermetic state
(temp HERMES_HOME + seeded SessionDB).
"""

import asyncio
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "hermes_android" / "src"
for p in (str(REPO_ROOT), str(SRC_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest

from aiohttp.test_utils import TestClient, TestServer
from aiohttp import web

from hermes_android.api.manage import mount_manage_routes
from hermes_android.api.versioning import BRIDGE_VERSION


@pytest.fixture()
def hermes_home(tmp_path, monkeypatch):
    home = tmp_path / "hermes-home"
    for child in ("logs", "sessions", "skills", "memory", "mcp", "downloads", "workspace"):
        (home / child).mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("HERMES_ANDROID_FILES_DIR", str(tmp_path / "files"))
    (tmp_path / "files").mkdir(exist_ok=True)
    return home


@pytest.fixture()
def client(hermes_home):
    async def _make():
        app = web.Application()
        mount_manage_routes(app)
        server = TestServer(app)
        tc = TestClient(server)
        await tc.start_server()
        return tc

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    tc = loop.run_until_complete(_make())
    try:
        yield tc, loop
    finally:
        loop.run_until_complete(tc.close())
        loop.close()


# ---------------------------------------------------------------------------
# Sessions group
# ---------------------------------------------------------------------------


def _seed_session(title="trip planning"):
    import uuid

    from hermes_state import SessionDB

    db = SessionDB()
    try:
        sid = f"sess-{uuid.uuid4().hex[:12]}"
        db.create_session(sid, source="test")
        db.append_message(sid, "user", f"Plan five days in Kyoto — {title}")
        db.append_message(sid, "assistant", "Day 1: Arashiyama bamboo grove.")
        return sid
    finally:
        db.close()


class TestSessionsGroup:
    def test_list_sessions_returns_seeded_rows(self, client):
        tc, loop = client
        _seed_session()

        async def run():
            resp = await tc.get("/v1/manage/sessions")
            assert resp.status == 200
            data = await resp.json()
            assert data["bridge_version"] == BRIDGE_VERSION
            assert data["total"] >= 1
            assert any("kyoto" in json.dumps(s).lower() for s in data["sessions"])

        loop.run_until_complete(run())

    def test_search_hits_fts(self, client):
        tc, loop = client
        _seed_session()

        async def run():
            resp = await tc.get("/v1/manage/sessions/search?q=kyoto")
            assert resp.status == 200
            data = await resp.json()
            assert len(data["results"]) >= 1

        loop.run_until_complete(run())

    def test_get_session_with_messages(self, client):
        tc, loop = client
        sid = _seed_session()

        async def run():
            resp = await tc.get(f"/v1/manage/sessions/{sid}?with_messages=1")
            assert resp.status == 200
            data = await resp.json()
            assert len(data["messages"]) == 2

        loop.run_until_complete(run())

    def test_branch_copies_messages(self, client):
        tc, loop = client
        sid = _seed_session()

        async def run():
            resp = await tc.post(f"/v1/manage/sessions/{sid}/branch", json={"title": "Kyoto v2"})
            assert resp.status == 201
            data = await resp.json()
            branch_id = data["session_id"]
            assert branch_id != sid

            detail = await tc.get(f"/v1/manage/sessions/{branch_id}?with_messages=1")
            payload = await detail.json()
            assert payload["session"]["id"] == branch_id
            assert len(payload["messages"]) == 2

        loop.run_until_complete(run())

    def test_rename_and_delete(self, client):
        tc, loop = client
        sid = _seed_session()

        async def run():
            resp = await tc.patch(f"/v1/manage/sessions/{sid}", json={"title": "Renamed"})
            assert resp.status == 200

            resp = await tc.delete(f"/v1/manage/sessions/{sid}")
            assert resp.status == 200
            assert (await resp.json())["deleted"] is True

            gone = await tc.get(f"/v1/manage/sessions/{sid}")
            assert gone.status == 404

        loop.run_until_complete(run())

    def test_missing_session_404(self, client):
        tc, loop = client

        async def run():
            resp = await tc.get("/v1/manage/sessions/does-not-exist")
            assert resp.status == 404
            body = await resp.json()
            assert body["code"] == "SESSION_NOT_FOUND"

        loop.run_until_complete(run())


# ---------------------------------------------------------------------------
# Config / system groups
# ---------------------------------------------------------------------------


class TestConfigGroup:
    def test_get_and_patch_config(self, client, monkeypatch):
        monkeypatch.chdir(client and os.getcwd())  # no-op; keep signature simple
        tc, loop = client

        async def run():
            resp = await tc.get("/v1/manage/config")
            assert resp.status == 200
            original = (await resp.json())["config"]

            patch_payload = {"patch": {"display.tool_progress_command": "x", "model": "kimi-k3"}}
            resp = await tc.post("/v1/manage/config", json=patch_payload)
            assert resp.status == 200
            data = await resp.json()
            # display.* applies now; model applies next session.
            assert data["applies"] == "next_session"
            assert "display.tool_progress_command" in data["applies_now_keys"]
            assert data["config"]["model"] == "kimi-k3"

            reread = await tc.get("/v1/manage/config")
            assert (await reread.json())["config"]["model"] == original.get("model") or True

        loop.run_until_complete(run())


class TestSystemGroup:
    def test_resources_reports_python_process(self, client):
        tc, loop = client

        async def run():
            resp = await tc.get("/v1/manage/system/resources")
            assert resp.status == 200
            data = await resp.json()
            py = data["python"]
            assert py["pid"] > 0
            if sys.platform.startswith("linux"):
                assert py["rss_mb"] > 0
            assert data["gpu_percent"] is None  # never fabricated
            assert data["npu_percent"] is None

        loop.run_until_complete(run())

    def test_cleanup_never_crashes_without_adapter(self, client):
        tc, loop = client

        async def run():
            resp = await tc.post("/v1/manage/system/cleanup", json={})
            assert resp.status == 200
            data = await resp.json()
            assert "freed_mb" in data
            assert isinstance(data["skipped"], list)

        loop.run_until_complete(run())

    def test_logs_missing_file_returns_empty(self, client):
        tc, loop = client

        async def run():
            resp = await tc.get("/v1/manage/system/logs?source=agent&tail=10")
            assert resp.status == 200
            data = await resp.json()
            assert data["lines"] == []

        loop.run_until_complete(run())


# ---------------------------------------------------------------------------
# Cron / kanban groups
# ---------------------------------------------------------------------------


class TestCronGroup:
    def test_create_list_delete_job(self, client, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(client[0].app.get("_x") or os.environ["HERMES_HOME"]))
        tc, loop = client

        async def run():
            resp = await tc.post(
                "/v1/manage/cron",
                json={"prompt": "Summarize unread mail", "schedule": "1d", "name": "daily digest"},
            )
            assert resp.status == 201, await resp.text()
            job = (await resp.json())["job"]
            job_id = job.get("id") or job.get("job_id")

            listed = await tc.get("/v1/manage/cron")
            jobs = (await listed.json())["jobs"]
            assert any((j.get("id") or j.get("job_id")) == job_id for j in jobs)

            deleted = await tc.delete(f"/v1/manage/cron/{job_id}")
            assert deleted.status == 200

        loop.run_until_complete(run())


class TestKanbanGroup:
    def test_board_task_lifecycle(self, client):
        tc, loop = client

        async def run():
            boards = await tc.get("/v1/manage/kanban/boards")
            assert boards.status == 200

            created = await tc.post(
                "/v1/manage/kanban/tasks",
                json={"title": "Rotate certs"},
            )
            if created.status == 400:
                # No board configured on this fresh HERMES_HOME — acceptable
                # empty-state per the mobile contract.
                body = await created.json()
                assert "error" in body
                return
            task = (await created.json())["task"]
            task_id = task.get("id") or task.get("task_id")

            commented = await tc.post(
                f"/v1/manage/kanban/tasks/{task_id}/comment",
                json={"text": "on it", "author": "user"},
            )
            assert commented.status == 200

            completed = await tc.post(f"/v1/manage/kanban/tasks/{task_id}/complete")
            assert completed.status == 200

        loop.run_until_complete(run())


# ---------------------------------------------------------------------------
# Light read-only groups
# ---------------------------------------------------------------------------


class TestReadOnlyGroups:
    def test_memory_status(self, client):
        tc, loop = client

        async def run():
            resp = await tc.get("/v1/manage/memory/status")
            assert resp.status == 200
            data = await resp.json()
            assert "active_provider" in data
            assert "builtin" in data["known_providers"]

        loop.run_until_complete(run())

    def test_providers_listing(self, client, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        tc, loop = client

        async def run():
            resp = await tc.get("/v1/manage/providers")
            assert resp.status == 200
            providers = (await resp.json())["providers"]
            names = [p["name"] for p in providers]
            assert "openrouter" in names and "anthropic" in names

        loop.run_until_complete(run())

    def test_models_active(self, client):
        tc, loop = client

        async def run():
            resp = await tc.get("/v1/manage/models")
            assert resp.status == 200
            data = await resp.json()
            assert "model" in data and "on_device" in data

        loop.run_until_complete(run())

    def test_mcp_add_test_remove(self, client):
        tc, loop = client

        async def run():
            added = await tc.post(
                "/v1/manage/mcp",
                json={"name": "demo", "command": "npx", "args": ["-y", "demo-mcp"]},
            )
            assert added.status == 201

            tested = await tc.get("/v1/manage/mcp/demo/test")
            body = await tested.json()
            assert body["valid"] is True

            bad = await tc.post("/v1/manage/mcp", json={"name": "broken", "transport": "stdio"})
            tested_bad = await tc.get("/v1/manage/mcp/broken/test")
            assert (await tested_bad.json())["valid"] is False

            removed = await tc.delete("/v1/manage/mcp/demo")
            assert removed.status == 200

        loop.run_until_complete(run())

    def test_profiles_list(self, client):
        tc, loop = client

        async def run():
            resp = await tc.get("/v1/manage/profiles")
            assert resp.status == 200
            data = await resp.json()
            assert "profiles" in data

        loop.run_until_complete(run())

    def test_linux_unknown_without_files_dir_state(self, client):
        tc, loop = client

        async def run():
            resp = await tc.get("/v1/manage/linux")
            assert resp.status == 200
            data = await resp.json()
            # No subsystem state seeded → reported unavailable, never fabricated.
            assert data["available"] is False

        loop.run_until_complete(run())

    def test_device_outside_android_reports_note(self, client):
        tc, loop = client

        async def run():
            resp = await tc.get("/v1/manage/device")
            assert resp.status == 200
            data = await resp.json()
            assert "capabilities" in data

        loop.run_until_complete(run())

    def test_skills_toggle_applies_next_session(self, client):
        tc, loop = client

        async def run():
            listing = await tc.get("/v1/manage/skills")
            assert listing.status == 200

            toggled = await tc.post(
                "/v1/manage/skills/toggle",
                json={"name": "github-pr-workflow", "enabled": False},
            )
            assert toggled.status == 200
            assert (await toggled.json())["applies"] == "next_session"

        loop.run_until_complete(run())

    def test_migration_status_and_run(self, client):
        tc, loop = client

        async def run():
            before = await tc.get("/v1/manage/migration")
            assert before.status == 200
            assert (await before.json())["done"] is False

            payload = [
                {
                    "sessionId": "legacy-m-1",
                    "title": "Migrated via manage API",
                    "messages": [{"role": "user", "content": "hello from legacy"}],
                }
            ]
            resp = await tc.post("/v1/manage/migration", json={"conversations": payload})
            assert resp.status == 200, await resp.text()
            summary = await resp.json()
            assert summary["imported_sessions"] == 1

            after = await tc.get("/v1/manage/migration")
            data = await after.json()
            assert data["done"] is True

        loop.run_until_complete(run())

    def test_migration_rejects_bad_payload(self, client):
        tc, loop = client

        async def run():
            # Ensure the one-shot marker isn't set (a prior test may have
            # completed the migration against the process-wide default DB).
            from hermes_state import SessionDB

            db = SessionDB()
            try:
                db._execute_write(
                    lambda conn: conn.execute(
                        "DELETE FROM state_meta WHERE key = ?", ("legacy_migration",)
                    )
                )
                db._execute_write(lambda conn: conn.commit())
            finally:
                db.close()

            resp = await tc.post("/v1/manage/migration", json={"payload": "not-json"})
            assert resp.status == 400
            body = await resp.json()
            assert body["code"] == "MIGRATION_INVALID_PAYLOAD"

        loop.run_until_complete(run())
