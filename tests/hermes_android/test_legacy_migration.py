"""Legacy ConversationStore → SessionDB migration tests.

Covers the P1 gate: seeded legacy store imported, relaunch skips via marker
(idempotent), attachments preserved as annotations, rollback on failure.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "hermes_android" / "src"
for p in (str(REPO_ROOT), str(SRC_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest

from hermes_android.migration.legacy import (
    MIGRATION_MARKER_KEY,
    import_legacy_conversations,
    migration_status,
)


def _legacy_payload() -> str:
    return json.dumps([
        {
            "sessionId": "legacy-abc-1",
            "title": "Kyoto trip",
            "updatedAtEpochMs": 1700000000000,
            "messages": [
                {"id": "m1", "role": "user", "content": "Plan Kyoto", "createdAtEpochMs": 1,
                 "attachments": []},
                {"id": "m2", "role": "assistant", "content": "Day 1: Arashiyama.", "createdAtEpochMs": 2,
                 "attachments": [
                     {"uri": "content://img", "displayName": "grove.jpg", "mimeType": "image/jpeg", "sizeBytes": 100},
                 ]},
            ],
        },
        {
            "sessionId": "legacy-abc-2",
            "title": "",
            "updatedAtEpochMs": 1700000001000,
            "messages": [],
        },
    ])


def _db(tmp_path):
    from hermes_state import SessionDB

    return SessionDB(tmp_path / "state.db")


def test_import_seeds_sessions_and_messages(tmp_path):
    summary = import_legacy_conversations(_legacy_payload(), db_path=tmp_path / "state.db")

    assert summary["skipped"] is False
    assert summary["imported_sessions"] == 1
    assert summary["empty_conversations"] == 1

    db = _db(tmp_path)
    try:
        sessions = db.list_sessions_rich(limit=50)
        migrated = [s for s in sessions if s.get("source") == "legacy_app"]
        assert len(migrated) == 1
        sid = migrated[0]["id"]
        messages = db.get_messages(sid)
        assert [m["role"] for m in messages] == ["user", "assistant"]
        # Attachment metadata is preserved as an annotation on content.
        assert "grove.jpg" in messages[1]["content"]
        title = db.get_session_title(sid)
        assert title == "Kyoto trip"
        # Marker row records completion.
        marker = json.loads(db.get_meta(MIGRATION_MARKER_KEY))
        assert marker["version"] == 1
    finally:
        db.close()


def test_rerun_is_idempotent_via_marker(tmp_path):
    first = import_legacy_conversations(_legacy_payload(), db_path=tmp_path / "s.db")
    assert first["skipped"] is False

    second = import_legacy_conversations(_legacy_payload(), db_path=tmp_path / "s.db")
    assert second["skipped"] is True
    assert second["reason"] == "already_migrated"

    status = migration_status(db_path=tmp_path / "s.db")
    assert status["done"] is True


def test_deterministic_ids_prevent_duplicate_import_within_one_run(tmp_path):
    payload = json.dumps([
        {"sessionId": "dup-1", "title": "A", "messages": [{"role": "user", "content": "hi"}]},
    ])
    summary = import_legacy_conversations(payload, db_path=tmp_path / "s.db")
    assert summary["imported_sessions"] == 1


def test_invalid_payload_raises_without_marker(tmp_path):
    with pytest.raises(ValueError):
        import_legacy_conversations("not json at all", db_path=tmp_path / "s.db")
    assert migration_status(db_path=tmp_path / "s.db")["done"] is False


def test_rollback_on_failure_restores_snapshot(tmp_path, monkeypatch):
    payload = json.dumps([
        {"sessionId": "rb-1", "title": "Before failure", "messages": [
            {"role": "user", "content": "hello"},
        ]},
    ])
    db_file = tmp_path / "s.db"

    summary = import_legacy_conversations(payload, db_path=db_file)
    assert summary["imported_sessions"] == 1

    # Force a mid-import failure by making set_meta blow up after inserts.
    from hermes_state import SessionDB as _SDB

    real_set_meta = _SDB.set_meta

    def exploding_set_meta(self, key, value):
        if key == MIGRATION_MARKER_KEY:
            raise RuntimeError("simulated crash during marker write")
        return real_set_meta(self, key, value)

    monkeypatch.setattr(_SDB, "set_meta", exploding_set_meta)

    # Reset the marker so the importer attempts a fresh run.
    db = _SDB(db_file)
    try:
        db._execute_write(
            lambda conn: conn.execute("DELETE FROM state_meta WHERE key = ?", (MIGRATION_MARKER_KEY,))
        )
        db._execute_write(lambda conn: conn.commit())
    finally:
        db.close()

    with pytest.raises(RuntimeError, match="simulated crash"):
        import_legacy_conversations(
            json.dumps([
                {"sessionId": "rb-2", "title": "Should roll back", "messages": [
                    {"role": "user", "content": "nope"},
                ]},
            ]),
            db_path=db_file,
        )
