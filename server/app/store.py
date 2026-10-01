"""SQLite store for contexts (one row per mark set, with the Q/A turn history)."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone

from app.config import settings

SCHEMA = """
create table if not exists contexts (
  id text primary key,
  created_at text not null,
  updated_at text not null,
  page_url text default '',
  page_title text default '',
  surface text default 'web',
  question text not null,
  marks_json text not null,
  resolution_json text not null,
  answer_json text not null
);
"""


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(settings.db_path)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    return connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create(
    page: dict, question: str, marks: list, resolution: dict, answer: dict
) -> str:
    context_id = uuid.uuid4().hex
    with connect() as db:
        db.execute(
            "insert into contexts values (?,?,?,?,?,?,?,?,?,?)",
            (
                context_id,
                _now(),
                _now(),
                page.get("url", ""),
                page.get("title", ""),
                page.get("surface", "web"),
                question,
                json.dumps(marks),
                json.dumps(resolution),
                json.dumps(answer),
            ),
        )
    return context_id


def update(context_id: str, resolution: dict, answer: dict) -> None:
    with connect() as db:
        db.execute(
            "update contexts set updated_at=?, resolution_json=?, answer_json=? where id=?",
            (_now(), json.dumps(resolution), json.dumps(answer), context_id),
        )


def get(context_id: str) -> dict | None:
    with connect() as db:
        row = db.execute("select * from contexts where id=?", (context_id,)).fetchone()
    return _serialize(row) if row else None


def recent(limit: int = 25) -> list[dict]:
    with connect() as db:
        rows = db.execute(
            "select * from contexts order by updated_at desc, rowid desc limit ?",
            (limit,),
        ).fetchall()
    return [_serialize(row) for row in rows]


def delete(context_id: str) -> bool:
    with connect() as db:
        return db.execute("delete from contexts where id=?", (context_id,)).rowcount > 0


def clear() -> int:
    with connect() as db:
        return db.execute("delete from contexts").rowcount


def _serialize(row: sqlite3.Row) -> dict:
    answer = json.loads(row["answer_json"])
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "question": row["question"],
        "page": {
            "url": row["page_url"],
            "title": row["page_title"],
            "surface": row["surface"],
        },
        "marks": json.loads(row["marks_json"]),
        "resolution": json.loads(row["resolution_json"]),
        "answer": answer,
        "turns": len(answer.get("history", [])),
    }
