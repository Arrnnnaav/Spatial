"""History retention: delete Ask logs and saved dictations older than N days. Enforced server-side so it applies
even when the dashboard is closed. Tasks and reminders are not pruned (the user manages those directly)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from app.config import settings

ALLOWED_DAYS = (None, 7, 30, 90, 365)  # None = keep forever
KEY = "retention_days"


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(settings.db_path)
    connection.execute(
        "create table if not exists prefs (key text primary key, value text)"
    )
    return connection


def get_days() -> int | None:
    with _connect() as db:
        row = db.execute("select value from prefs where key=?", (KEY,)).fetchone()
    return int(row[0]) if row and row[0] else None


def set_days(days: int | None) -> None:
    if days not in ALLOWED_DAYS:
        raise ValueError("unsupported retention window")
    with _connect() as db:
        db.execute(
            "insert or replace into prefs values (?, ?)",
            (KEY, "" if days is None else str(days)),
        )


def prune() -> dict:
    """Delete rows older than the configured window. Timestamps are UTC ISO strings, so string comparison is exact."""
    days = get_days()
    if days is None:
        return {"asks": 0, "dictations": 0}
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(
        timespec="seconds"
    )
    with _connect() as db:
        # tables are created lazily by their own modules; ignore a table that does not exist yet
        counts = {}
        for name, table, column in (
            ("asks", "contexts", "updated_at"),
            ("dictations", "dictations", "created_at"),
        ):
            try:
                counts[name] = db.execute(
                    f"delete from {table} where {column} < ?", (cutoff,)
                ).rowcount
            except sqlite3.OperationalError:
                counts[name] = 0
    return counts
