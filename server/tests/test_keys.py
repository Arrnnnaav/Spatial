import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

import pytest
from fastapi.testclient import TestClient

from app import config, keys, main

SECRET = "sk-test-0123456789abcdef"


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    path = tmp_path / "server.env"
    monkeypatch.setattr(config, "user_env_path", lambda: path)
    for name in keys.ALLOWED:
        monkeypatch.delenv(name, raising=False)
    return path


@pytest.fixture
def client(env_file, monkeypatch):
    monkeypatch.setattr(main.settings, "api_token", "secret", raising=False)
    monkeypatch.setattr(
        main.desktop, "token_ok", lambda token: token == "dt", raising=False
    )
    with TestClient(main.app) as c:
        c.headers.update({"Authorization": "Bearer secret", "X-Spatial-Desktop": "dt"})
        yield c


def test_status_lists_every_allowed_key_as_a_boolean_and_never_a_value(
    client, monkeypatch
):
    monkeypatch.setenv("OPENROUTER_API_KEY", SECRET)
    body = client.get("/api/keys").json()
    assert set(body) == set(keys.ALLOWED)
    assert body["OPENROUTER_API_KEY"] is True and body["OPENAI_API_KEY"] is False
    assert SECRET not in client.get("/api/keys").text


def test_put_writes_the_per_user_file_preserves_other_lines_and_never_echoes(
    client, env_file
):
    env_file.write_text("# keep me\nTAVILY_API_KEY=tvly-0123456789\n", encoding="utf-8")
    response = client.put("/api/keys", json={"name": "OPENAI_API_KEY", "value": SECRET})
    assert response.status_code == 200 and response.json() == {
        "name": "OPENAI_API_KEY",
        "configured": True,
        "restart_required": True,
    }
    assert SECRET not in response.text
    lines = env_file.read_text(encoding="utf-8").splitlines()
    assert (
        "# keep me" in lines
        and "TAVILY_API_KEY=tvly-0123456789" in lines
        and f"OPENAI_API_KEY={SECRET}" in lines
    )
    assert (
        os.environ["OPENAI_API_KEY"] == SECRET
    )  # status reflects it at once; providers pick it up on restart
    client.put(
        "/api/keys", json={"name": "OPENAI_API_KEY", "value": SECRET + "x"}
    )  # replace, not duplicate
    assert (
        sum(
            line.startswith("OPENAI_API_KEY=")
            for line in env_file.read_text(encoding="utf-8").splitlines()
        )
        == 1
    )


def test_empty_value_removes_the_key(client, env_file):
    client.put("/api/keys", json={"name": "NVIDIA_API_KEY", "value": SECRET})
    done = client.put("/api/keys", json={"name": "NVIDIA_API_KEY", "value": ""})
    assert done.json()["configured"] is False
    assert "NVIDIA_API_KEY" not in env_file.read_text(encoding="utf-8")
    assert "NVIDIA_API_KEY" not in os.environ


@pytest.mark.parametrize(
    "name,value",
    [
        ("PATH", SECRET),  # only known provider keys
        ("OPENAI_API_KEY", "short"),  # too short to be a key
        ("OPENAI_API_KEY", "has space 0123456789"),
        ("OPENAI_API_KEY", "line\nbreak0123456789"),
        ("OPENAI_API_KEY", 'quote"0123456789'),
        ("OPENAI_API_KEY", "x" * 500),
    ],
)
def test_invalid_names_and_values_are_rejected(client, env_file, name, value):
    assert (
        client.put("/api/keys", json={"name": name, "value": value}).status_code == 422
    )
    assert not env_file.exists() or "=" not in env_file.read_text(encoding="utf-8")


def test_written_file_round_trips_through_the_startup_loader(
    client, env_file, monkeypatch
):
    client.put("/api/keys", json={"name": "ANTHROPIC_API_KEY", "value": SECRET})
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    config.load_user_env(env_file)
    assert os.environ["ANTHROPIC_API_KEY"] == SECRET
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def test_routes_need_both_tokens(client):
    web = TestClient(main.app)
    web.headers.update({"Authorization": "Bearer secret"})
    assert web.get("/api/keys").status_code == 403
    assert (
        web.put(
            "/api/keys", json={"name": "OPENAI_API_KEY", "value": SECRET}
        ).status_code
        == 403
    )
