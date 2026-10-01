import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ["SPATIAL_DB"] = str(Path(__file__).parent / "test_spatial.db")
sys.path.insert(0, str(Path(__file__).parents[1]))

import pytest
from fastapi.testclient import TestClient

from app import dictations, main, retention, store


def ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(
        timespec="seconds"
    )


@pytest.fixture(autouse=True)
def clean():
    store.clear()
    dictations.clear()
    retention.set_days(None)
    yield
    store.clear()
    dictations.clear()
    retention.set_days(None)


def seed():
    """One old and one fresh row in each table."""
    old_ctx = store.create({"title": "old"}, "q", [], {}, {"history": []})
    new_ctx = store.create({"title": "new"}, "q", [], {}, {"history": []})
    old_d = dictations.create("old note", "Old", "s")["id"]
    new_d = dictations.create("new note", "New", "s")["id"]
    with store.connect() as db:
        db.execute("update contexts set updated_at=? where id=?", (ago(100), old_ctx))
    with dictations._connect() as db:
        db.execute("update dictations set created_at=? where id=?", (ago(100), old_d))
    return old_ctx, new_ctx, old_d, new_d


def test_prune_removes_only_rows_older_than_the_window():
    old_ctx, new_ctx, old_d, new_d = seed()
    retention.set_days(90)
    assert retention.prune() == {"asks": 1, "dictations": 1}
    assert store.get(old_ctx) is None and store.get(new_ctx) is not None
    assert dictations.get(old_d) is None and dictations.get(new_d) is not None


def test_forever_keeps_everything_and_prune_is_a_no_op():
    seed()
    assert retention.get_days() is None
    assert retention.prune() == {"asks": 0, "dictations": 0}
    assert len(store.recent(10)) == 2 and len(dictations.list_recent(10)) == 2


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main.settings, "api_token", "secret", raising=False)
    monkeypatch.setattr(
        main.desktop, "token_ok", lambda token: token == "dt", raising=False
    )
    with TestClient(main.app) as c:
        c.headers.update({"Authorization": "Bearer secret", "X-Spatial-Desktop": "dt"})
        yield c


def test_route_sets_prunes_immediately_and_rejects_odd_values(client):
    seed()
    assert client.get("/api/retention").json() == {"days": None}
    assert (
        client.put("/api/retention", json={"days": 45}).status_code == 422
    )  # only the offered choices
    assert client.put("/api/retention", json={"days": 0}).status_code == 422
    done = client.put("/api/retention", json={"days": 90}).json()
    assert done == {"days": 90, "pruned": {"asks": 1, "dictations": 1}}
    assert client.get("/api/retention").json() == {"days": 90}
    assert client.put("/api/retention", json={"days": None}).json()["days"] is None


def test_route_needs_both_tokens(client):
    web = TestClient(main.app)
    web.headers.update({"Authorization": "Bearer secret"})
    assert web.get("/api/retention").status_code == 403
    assert web.put("/api/retention", json={"days": 30}).status_code == 403
