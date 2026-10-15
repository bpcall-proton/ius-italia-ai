from __future__ import annotations

from app.seed import DEMO_LAWYER

from .conftest import admin_login, login


def test_health(client):
    assert client.get("/health").json()["ok"] is True


def test_lawyer_login_and_me(client):
    h = login(client)
    me = client.get("/me", headers=h).json()
    assert me["email"] == DEMO_LAWYER[0]
    assert me["subscription"]["plan_code"] == "PRO"
    assert me["credits"]["balance"] == 300


def test_wrong_password_and_throttle(client):
    for _ in range(5):
        assert client.post("/auth/login", json={"email": DEMO_LAWYER[0], "password": "x"}).status_code == 401
    assert client.post("/auth/login", json={"email": DEMO_LAWYER[0], "password": DEMO_LAWYER[1]}).status_code == 429


def test_lawyer_cannot_access_admin(client):
    h = login(client)
    assert client.get("/admin/dashboard", headers=h).status_code == 403


def test_admin_requires_mfa(client):
    r = client.post("/auth/login", json={"email": "admin@demo.ius", "password": "Demo-Admin-2026"})
    body = r.json()
    assert "access_token" not in body and body["mfa_setup_required"]
    bad = client.post("/auth/mfa", json={"challenge": body["challenge"], "code": "000000"})
    assert bad.status_code == 401


def test_admin_dashboard_and_lawyers(client):
    h = admin_login(client)
    d = client.get("/admin/dashboard", headers=h).json()
    assert d["registered"] == 3 and d["paying"] == 2
    assert d["mrr_cents"] == 1900 + 7900
    lawyers = client.get("/admin/lawyers", headers=h).json()
    assert {lw["email"] for lw in lawyers} >= {DEMO_LAWYER[0]}


def test_admin_cannot_use_lawyer_ai(client):
    h = admin_login(client)
    assert client.get("/ai/providers", headers=h).status_code == 403


def test_session_revocation(client):
    h = login(client)
    sessions = client.get("/auth/sessions", headers=h).json()
    assert len(sessions) == 1
    assert client.post(f"/auth/sessions/{sessions[0]['id']}/revoke", headers=h).status_code == 200
    assert client.get("/me", headers=h).status_code == 401


def test_suspend_blocks_login_and_is_audited(client):
    h = admin_login(client)
    lawyer = next(lw for lw in client.get("/admin/lawyers", headers=h).json() if lw["email"] == DEMO_LAWYER[0])
    lh = login(client)
    assert (
        client.post(f"/admin/lawyers/{lawyer['id']}/status", json={"status": "suspended"}, headers=h).status_code == 200
    )
    assert client.get("/me", headers=lh).status_code == 401
    assert client.post("/auth/login", json={"email": DEMO_LAWYER[0], "password": DEMO_LAWYER[1]}).status_code == 403
    audit = client.get("/admin/audit", headers=h).json()
    assert audit[0]["action"] == "lawyer_status"


def test_price_change_is_versioned_not_retroactive(client):
    h = admin_login(client)
    r = client.post(
        "/admin/plans/PRO/versions",
        json={"price_month_cents": 4900, "monthly_credits": 350, "monthly_token_limit": 700000},
        headers=h,
    )
    assert r.status_code == 200 and r.json()["version"] == 2
    pro = next(p for p in client.get("/admin/plans", headers=h).json() if p["code"] == "PRO")
    assert [v["price_month_cents"] for v in pro["versions"]] == [3900, 4900]
    me = client.get("/me", headers=login(client)).json()
    assert me["subscription"]["version"]["price_month_cents"] == 3900
    assert next(p for p in client.get("/plans").json() if p["code"] == "PRO")["current"]["price_month_cents"] == 4900


def test_bonus_credits_idempotent(client):
    h = admin_login(client)
    firm = next(lw for lw in client.get("/admin/lawyers", headers=h).json() if lw["email"] == DEMO_LAWYER[0])["firm"]
    body = {"amount": 50, "idempotency_key": "bonus-test-001"}
    first = client.post(f"/admin/firms/{firm['id']}/credits", json=body, headers=h).json()
    second = client.post(f"/admin/firms/{firm['id']}/credits", json=body, headers=h).json()
    assert first["applied"] and not second["applied"]
    assert second["balance"] == 350


def test_simulated_usage_is_flagged(client):
    h = admin_login(client)
    usage = client.get("/admin/ai-usage", headers=h).json()
    assert usage["records"] and all(r["simulated"] for r in usage["records"])
