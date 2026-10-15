from __future__ import annotations

import json

import pyotp
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.seed import DEMO_ADMIN, DEMO_LAWYER


@pytest.fixture
def app(tmp_path):
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        data_dir=tmp_path,
        jwt_secret="test-secret-not-for-production-0123456789",
        seed_demo=True,
    )
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def login(client, email=DEMO_LAWYER[0], password=DEMO_LAWYER[1]) -> dict:
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def admin_login(client) -> dict:
    r = client.post("/auth/login", json={"email": DEMO_ADMIN[0], "password": DEMO_ADMIN[1]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("mfa_setup_required") or body.get("mfa_required")
    secret = body.get("secret") or admin_login.secret
    admin_login.secret = secret
    r = client.post("/auth/mfa", json={"challenge": body["challenge"], "code": pyotp.TOTP(secret).now()})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


admin_login.secret = None


def consent(client, headers, provider="simulation", operation="analyze") -> str:
    r = client.post(
        "/ai/consents",
        json={"provider": provider, "operation": operation, "data_categories": ["descrizione caso"], "char_count": 100},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def sse_events(text: str) -> list[tuple[str, dict]]:
    out = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "event" in lines:
            out.append((lines["event"], json.loads(lines["data"])))
    return out
