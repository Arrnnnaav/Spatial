"""Saved dictation entries (final transcript + metadata) in the local SQLite database. Audio is never stored."""

from __future__ import annotations

import re
import sqlite3
import uuid
from datetime import datetime, timezone

from app.config import settings

SCHEMA = """
create table if not exists dictations (
  id text primary key,
  created_at text not null,
  title text not null,
  summary text not null,
  text text not null,
  source_app text default '',
  source_title text default '',
  stt_provider text default '',
  cleanup_provider text default ''
);
"""
EDITABLE = ("title", "summary", "text")


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(settings.db_path)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    return connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fallback_meta(text: str) -> tuple[str, str]:
    """Deterministic title/summary used when no provider can write them."""
    flat = re.sub(r"\s+", " ", text or "").strip()
    if not flat:
        return "Dictation", "Empty dictation"
    words = flat.split(" ")
    title = " ".join(words[:8]).rstrip(".,;:!?")[:60].rstrip()
    first = re.split(r"(?<=[.!?])\s", flat, maxsplit=1)[0]
    summary = first if len(first) <= 140 else first[:137].rstrip() + "…"
    return title or "Dictation", summary


def create(
    text: str,
    title: str,
    summary: str,
    source_app: str = "",
    source_title: str = "",
    stt_provider: str = "",
    cleanup_provider: str = "",
) -> dict:
    entry_id = uuid.uuid4().hex
    with _connect() as db:
        db.execute(
            "insert into dictations values (?,?,?,?,?,?,?,?,?)",
            (
                entry_id,
                _now(),
                title,
                summary,
                text,
                source_app,
                source_title,
                stt_provider,
                cleanup_provider,
            ),
        )
    return get(entry_id)


def get(entry_id: str) -> dict | None:
    with _connect() as db:
        row = db.execute("select * from dictations where id=?", (entry_id,)).fetchone()
    return dict(row) if row else None


def list_recent(limit: int = 50) -> list[dict]:
    with _connect() as db:
        rows = db.execute(
            "select * from dictations order by created_at desc, rowid desc limit ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def update(entry_id: str, **fields) -> dict | None:
    changes = {k: v for k, v in fields.items() if k in EDITABLE and v is not None}
    if changes:
        assignments = ", ".join(f"{k}=?" for k in changes)
        with _connect() as db:
            db.execute(
                f"update dictations set {assignments} where id=?",
                (*changes.values(), entry_id),
            )
    return get(entry_id)


def delete(entry_id: str) -> bool:
    with _connect() as db:
        return db.execute("delete from dictations where id=?", (entry_id,)).rowcount > 0


def clear() -> int:
    with _connect() as db:
        return db.execute("delete from dictations").rowcount
