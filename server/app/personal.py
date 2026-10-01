"""Personal tasks/notes and reminders in the local SQLite database. Text never leaves this device."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone

from app.config import settings

SCHEMA = """
create table if not exists tasks (
  id text primary key,
  created_at text not null,
  text text not null,
  note text not null default '',
  done integer not null default 0,
  done_at text
);
create table if not exists reminders (
  id text primary key,
  created_at text not null,
  due_at text not null,
  text text not null,
  task_id text,
  fired_at text
);
"""


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(settings.db_path)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    return connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_due(value: str) -> str:
    """Timezone-aware ISO time -> UTC ISO string. Raises ValueError for naive or invalid input."""
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("due_at needs a timezone")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def _task(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    item = dict(row)
    item["done"] = bool(item["done"])
    return item


def add_task(text: str, note: str = "") -> dict:
    task_id = uuid.uuid4().hex
    with _connect() as db:
        db.execute(
            "insert into tasks (id, created_at, text, note) values (?,?,?,?)",
            (task_id, _now(), text, note),
        )
    return get_task(task_id)


def get_task(task_id: str) -> dict | None:
    with _connect() as db:
        return _task(
            db.execute("select * from tasks where id=?", (task_id,)).fetchone()
        )


def list_tasks(limit: int = 200) -> list[dict]:
    with _connect() as db:
        rows = db.execute(
            "select * from tasks order by done asc, created_at desc, rowid desc limit ?",
            (limit,),
        ).fetchall()
    return [_task(row) for row in rows]


def update_task(
    task_id: str,
    text: str | None = None,
    note: str | None = None,
    done: bool | None = None,
) -> dict | None:
    changes: dict = {}
    if text is not None:
        changes["text"] = text
    if note is not None:
        changes["note"] = note
    if done is not None:
        changes["done"] = int(done)
        changes["done_at"] = _now() if done else None
    if changes:
        assignments = ", ".join(f"{k}=?" for k in changes)
        with _connect() as db:
            db.execute(
                f"update tasks set {assignments} where id=?",
                (*changes.values(), task_id),
            )
    return get_task(task_id)


def delete_task(task_id: str) -> bool:
    with _connect() as db:
        return db.execute("delete from tasks where id=?", (task_id,)).rowcount > 0


def add_reminder(text: str, due_at: str, task_id: str | None = None) -> dict:
    reminder_id = uuid.uuid4().hex
    with _connect() as db:
        db.execute(
            "insert into reminders (id, created_at, due_at, text, task_id) values (?,?,?,?,?)",
            (reminder_id, _now(), parse_due(due_at), text, task_id),
        )
    return get_reminder(reminder_id)


def get_reminder(reminder_id: str) -> dict | None:
    with _connect() as db:
        row = db.execute(
            "select * from reminders where id=?", (reminder_id,)
        ).fetchone()
    return dict(row) if row else None


def list_reminders(limit: int = 200) -> list[dict]:
    with _connect() as db:
        rows = db.execute(
            "select * from reminders order by due_at asc, rowid asc limit ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


def due_reminders(now: str | None = None) -> list[dict]:
    with _connect() as db:
        rows = db.execute(
            "select * from reminders where fired_at is null and due_at <= ? order by due_at asc",
            (now or _now(),),
        ).fetchall()
    return [dict(row) for row in rows]


def mark_fired(reminder_id: str) -> dict | None:
    with _connect() as db:
        db.execute(
            "update reminders set fired_at=? where id=? and fired_at is null",
            (_now(), reminder_id),
        )
    return get_reminder(reminder_id)


def delete_reminder(reminder_id: str) -> bool:
    with _connect() as db:
        return (
            db.execute("delete from reminders where id=?", (reminder_id,)).rowcount > 0
        )


def clear_all() -> None:
    with _connect() as db:
        db.execute("delete from tasks")
        db.execute("delete from reminders")
