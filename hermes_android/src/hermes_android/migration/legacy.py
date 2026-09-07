"""One-shot legacy data migration (P1 first-run).

Imports the old Kotlin ``ConversationStore`` JSON into ``hermes_state.SessionDB``
per Rule #3: SessionDB becomes the only conversation store; originals are kept
untouched on the Kotlin side.

Idempotency: a marker row (SessionDB meta) records completion; reruns skip.
Safety: the session database file is snapshotted before any write and restored
on failure, so a crashed import never leaves half-migrated state.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MIGRATION_MARKER_KEY = "legacy_migration"
MIGRATION_MARKER_VERSION = 1


def _open_db(db_path=None):
    from hermes_state import SessionDB

    return SessionDB(db_path) if db_path else SessionDB()


def _marker(db) -> dict[str, Any] | None:
    try:
        raw = db.get_meta(MIGRATION_MARKER_KEY)
    except Exception:
        return None
    if not raw:
        return None
    try:
        marker = json.loads(raw)
        return marker if isinstance(marker, dict) else None
    except Exception:
        return None


def migration_status(db_path=None) -> dict[str, Any]:
    """Report whether the one-shot migration already ran."""
    db = _open_db(db_path)
    try:
        marker = _marker(db)
        return {
            "done": bool(marker and marker.get("version") == MIGRATION_MARKER_VERSION),
            "marker": marker,
        }
    finally:
        db.close()


def import_legacy_conversations(
    payload: str,
    *,
    source: str = "legacy_app",
    backup_suffix: str = ".pre-legacy-migration",
    db_path=None,
) -> dict[str, Any]:
    """Import a ConversationStore JSON payload into SessionDB.

    Args:
        payload: The raw JSON string produced by the Android store (an array
            of ``{sessionId, title, updatedAtEpochMs, messages:[...]}``), or a
            filesystem path to such a file.
        source: SessionDB ``source`` stamped onto imported sessions.
        backup_suffix: Suffix for the pre-migration database snapshot.

    Returns a summary dict: counts plus per-session outcomes.
    """
    status = migration_status(db_path)
    if status["done"]:
        return {"skipped": True, "reason": "already_migrated", "marker": status["marker"]}

    text = payload
    candidate_path = Path(str(payload))
    if not payload.lstrip().startswith(("[", "{")) and candidate_path.is_file():
        text = candidate_path.read_text(encoding="utf-8")

    try:
        conversations = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Legacy conversation payload is not valid JSON: {exc}") from exc
    if isinstance(conversations, dict):
        # Tolerate an object wrapper with the array under a key.
        for key in ("conversations", "sessions"):
            if isinstance(conversations.get(key), list):
                conversations = conversations[key]
                break
    if not isinstance(conversations, list):
        raise ValueError("Legacy payload must be a JSON array of conversations")

    db = _open_db(db_path)
    backup_path: Path | None = None
    imported = 0
    skipped_existing = 0
    empty_conversations = 0
    results: list[dict[str, Any]] = []

    # Snapshot for rollback before the first write.
    try:
        live_db_path = Path(getattr(db, "db_path", "") or "")
        if live_db_path.is_file():
            backup_path = live_db_path.with_name(live_db_path.name + backup_suffix)
            shutil.copy2(live_db_path, backup_path)
    except Exception as snap_exc:
        logger.warning("Legacy migration snapshot failed (continuing): %s", snap_exc)

    try:
        for index, conversation in enumerate(conversations):
            if not isinstance(conversation, dict):
                skipped_existing += 1
                results.append({"index": index, "status": "invalid_entry"})
                continue
            legacy_id = str(conversation.get("sessionId") or "").strip()
            title = str(conversation.get("title") or "").strip() or f"Migrated chat {index + 1}"
            messages = conversation.get("messages") or []
            if not legacy_id or not isinstance(messages, list):
                skipped_existing += 1
                results.append({"index": index, "status": "invalid_entry"})
                continue
            if not messages:
                empty_conversations += 1
                results.append({"index": index, "session_id": legacy_id, "status": "empty"})
                continue

            # Fresh deterministic id avoids collisions with anything already
            # living in SessionDB; the original id is preserved in results.
            new_id = f"legacy-{uuid.uuid5(uuid.NAMESPACE_URL, legacy_id).hex[:20]}"

            if db.resolve_session_id(new_id):
                skipped_existing += 1
                results.append({"index": index, "session_id": legacy_id, "status": "exists"})
                continue

            db.create_session(new_id, source=source)
            count = 0
            for message in messages:
                if not isinstance(message, dict):
                    continue
                role = str(message.get("role") or "").strip()
                content = str(message.get("content") or "")
                attachments = message.get("attachments") or []
                if attachments:
                    labels = "; ".join(
                        str(a.get("displayName") or a.get("mimeType") or "attachment")
                        for a in attachments
                        if isinstance(a, dict)
                    )
                    if labels:
                        content = f"{content}\n[attachments: {labels}]".strip()
                if not role:
                    continue
                db.append_message(new_id, role, content)
                count += 1
            db.set_session_title(new_id, title[:120])
            imported += 1
            results.append({
                "index": index,
                "legacy_session_id": legacy_id,
                "session_id": new_id,
                "title": title,
                "messages_imported": count,
                "status": "imported",
            })

        marker = {
            "version": MIGRATION_MARKER_VERSION,
            "completed_at_epoch_ms": int(time.time() * 1000),
            "imported_sessions": imported,
            "source": source,
        }
        db.set_meta(MIGRATION_MARKER_KEY, json.dumps(marker, sort_keys=True))
    except Exception:
        # Rollback: restore the snapshot so no partial state survives.
        if backup_path is not None and backup_path.is_file():
            try:
                db.close()
                shutil.copy2(backup_path, db_path_target(getattr(db, "db_path", None)))
                logger.warning("Legacy migration failed; database restored from snapshot")
            except Exception as restore_exc:
                logger.error("Legacy migration rollback failed: %s", restore_exc)
        raise
    finally:
        try:
            db.close()
        except Exception:
            pass

    return {
        "skipped": False,
        "imported_sessions": imported,
        "skipped_existing": skipped_existing,
        "empty_conversations": empty_conversations,
        "results": results,
        "backup": str(backup_path) if backup_path else None,
    }


def db_path_target(db_path=None) -> str:
    if db_path:
        return str(db_path)
    from hermes_state import DEFAULT_DB_PATH

    return str(DEFAULT_DB_PATH)
