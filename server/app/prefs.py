"""Tiny key/value preferences in the local SQLite database (shared `prefs` table, also used by retention.py)."""
from __future__ import annotations

import sqlite3

from app.config import settings


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(settings.db_path)
    connection.execute("create table if not exists prefs (key text primary key, value text)")
    return connection


def get(key: str, default: str = "") -> str:
    with _connect() as db:
        row = db.execute("select value from prefs where key=?", (key,)).fetchone()
    return row[0] if row and row[0] is not None else default


def set(key: str, value: str) -> None:  # noqa: A001 - mirrors dict-style API
    with _connect() as db:
        db.execute("insert or replace into prefs values (?, ?)", (key, value))
