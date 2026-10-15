from tests.conftest import admin_login, login


def test_ricarica_crediti_approvata_dall_admin(client):
    h = login(client)
    before = client.get("/me", headers=h).json()["credits"]["balance"]
    r = client.post("/credits/topups", headers=h, json={"credits": 1000})
    assert r.status_code == 200, r.text
    assert client.post("/credits/topups", headers=h, json={"credits": 500}).status_code == 409
    tid = r.json()["id"]
    assert client.post(f"/admin/topups/{tid}/approve", headers=h).status_code in (401, 403)
    a = admin_login(client)
    assert any(t["id"] == tid for t in client.get("/admin/topups", headers=a).json())
    ok = client.post(f"/admin/topups/{tid}/approve", headers=a)
    assert ok.status_code == 200, ok.text
    assert client.post(f"/admin/topups/{tid}/approve", headers=a).status_code == 409
    assert client.get("/me", headers=h).json()["credits"]["balance"] == before + 1000
    assert client.get("/credits/topups", headers=h).json()[0]["status"] == "approvata"
