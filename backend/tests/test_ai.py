from __future__ import annotations

import json
import threading

from sqlalchemy import text

from app import billing
from app.models import CreditWallet, User

from .conftest import admin_login, consent, login, sse_events

CASE_2019 = (
    "Nel 2019 una persona apre una partita IVA a nome della sorella, sostenendo un consenso telefonico. "
    "Nel 2026 la sorella denuncia una sostituzione di persona. "
    "Esistono documenti firmati e comunicazioni con il commercialista."
)


def run_analysis(client, h, description=CASE_2019, request_id=None):
    body = {"consent_id": consent(client, h), "description": description}
    if request_id:
        body["request_id"] = request_id
    r = client.post("/ai/analyze", json=body, headers=h)
    return r, sse_events(r.text) if r.status_code == 200 else []


def test_case_2019_prioritizes_494_and_prescription(client):
    h = login(client)
    r, events = run_analysis(client, h)
    assert r.status_code == 200
    steps = [d["label"] for e, d in events if e == "step"]
    assert steps == [
        "Preparazione quesito",
        "Ricerca fonti",
        "Fonti recuperate",
        "Analisi in generazione",
        "Controllo citazioni",
        "Piano d'azione pronto",
    ]
    result = next(d for e, d in events if e == "result")
    assert result["simulated"] is True
    data = result["data"]
    cites = [n["citation"] for n in data["candidate_norms"]]
    assert cites[0] == "art. 494 c.p."
    for art in ("157", "158", "159", "160", "161"):
        assert f"art. {art} c.p." in cites
    dump = json.dumps(data, ensure_ascii=False).lower()
    assert "564" not in dump and "incesto" not in dump
    assert "è prescritto" not in dump and "reato è integrato" not in dump
    assert "non è possibile stabilire" in dump
    assert data["case_law"] == []
    assert all(n["verified_text"] is False for n in data["candidate_norms"])
    assert data["citation_check"] == []


def test_unrelated_case_does_not_get_penal_norms(client):
    h = login(client)
    _, events = run_analysis(
        client, h, "Il cliente lamenta il mancato pagamento di tre fatture previste dal contratto."
    )
    data = next(d for e, d in events if e == "result")["data"]
    cites = [n["citation"] for n in data["candidate_norms"]]
    assert "art. 1218 c.c." in cites
    assert not any(c.endswith("c.p.") for c in cites)


def test_without_consent_nothing_is_processed(client):
    h = login(client)
    r = client.post("/ai/analyze", json={"consent_id": "inesistente", "description": CASE_2019}, headers=h)
    assert r.status_code == 403


def test_revoked_consent_blocks_new_transmissions(client):
    h = login(client)
    cid = consent(client, h)
    assert client.post(f"/ai/consents/{cid}/revoke", headers=h).status_code == 200
    r = client.post("/ai/analyze", json={"consent_id": cid, "description": CASE_2019}, headers=h)
    assert r.status_code == 403


def test_external_provider_not_configured_is_declared(client):
    h = login(client)
    providers = {p["name"]: p for p in client.get("/ai/providers", headers=h).json()}
    assert providers["simulation"]["status"] == "attivo"
    assert providers["openai"]["status"] == "non configurato"
    assert providers["deepseek"]["status"] == "non configurato"
    cid = consent(client, h, provider="openai")
    r = client.post("/ai/analyze", json={"consent_id": cid, "provider": "openai", "description": CASE_2019}, headers=h)
    assert r.status_code == 503


def test_usage_recorded_and_credits_charged(client, app):
    h = login(client)
    before = client.get("/me", headers=h).json()["credits"]["balance"]
    run_analysis(client, h, request_id="req-usage-1")
    me = client.get("/me", headers=h).json()
    assert me["credits"]["reserved"] == 0
    rec = next(
        r
        for r in client.get("/admin/ai-usage", headers=admin_login(client)).json()["records"]
        if r["request_id"] == "req-usage-1"
    )
    assert rec["total_tokens"] == rec["input_tokens"] + rec["output_tokens"] > 0
    assert rec["credits"] == before - me["credits"]["balance"] > 0
    assert rec["simulated"] is True


def test_duplicate_request_id_not_charged_twice(client):
    h = login(client)
    r1, _ = run_analysis(client, h, request_id="dup-1")
    balance = client.get("/me", headers=h).json()["credits"]["balance"]
    r2, _ = run_analysis(client, h, request_id="dup-1")
    assert r1.status_code == 200 and r2.status_code == 409
    assert client.get("/me", headers=h).json()["credits"]["balance"] == balance


def test_insufficient_credits_blocks_only_ai(client, app):
    h = login(client)
    with app.state.db.SessionLocal() as db:
        db.execute(text("UPDATE credit_wallets SET balance = 2"))
        db.commit()
    r, _ = run_analysis(client, h)
    assert r.status_code == 402
    assert client.get("/me", headers=h).status_code == 200


def test_concurrent_reservations_never_exceed_budget(client, app):
    login(client)
    with app.state.db.SessionLocal() as db:
        user = db.query(User).filter(User.email == "avvocato@demo.ius").one()
        firm_id = user.firm_id
        db.execute(text("UPDATE credit_wallets SET balance = 30 WHERE firm_id = :f"), {"f": firm_id})
        db.commit()
    ok, errors = [], []

    def worker(i):
        with app.state.db.SessionLocal() as db:
            try:
                billing.reserve(db, firm_id=firm_id, request_id=f"conc-{i}", credits=6, max_tokens=10)
                ok.append(i)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    with app.state.db.SessionLocal() as db:
        w = db.query(CreditWallet).filter(CreditWallet.firm_id == firm_id).one()
        assert len(ok) == 5 and w.balance == 0 and w.reserved == 30


def test_draft_only_uses_approved_brief(client):
    h = login(client)
    cid = consent(client, h, operation="draft")
    brief = {
        "doc_type": "richiesta_documenti",
        "recipient": "Sig.ra Anna Esempio",
        "subject": "Documenti per la pratica",
        "approved_facts": ["Il 10 marzo 2019 è stata aperta una partita IVA."],
        "requests": ["Copia dei documenti firmati"],
        "approved_norm_ids": ["cp-494", "cp-999"],
        "due_days": 10,
    }
    r = client.post("/ai/draft", json={"consent_id": cid, "brief": brief}, headers=h)
    data = next(d for e, d in sse_events(r.text) if e == "result")["data"]
    assert "Il 10 marzo 2019 è stata aperta una partita IVA." in data["html"]
    assert "art. 494 c.p." in data["html"]
    assert "999" not in data["html"]
    assert "commercialista" not in data["html"]
    assert data["missing_fields"] == ["mittente"]
    assert "[DA COMPLETARE: avvocato mittente]" in data["html"]


def test_backend_never_stores_case_content(client, app):
    h = login(client)
    canary = "CANARY-RISERVATO-7f3a9"
    run_analysis(client, h, description=f"{CASE_2019} Nome del cliente: {canary}.")
    cid = consent(client, h, operation="draft")
    client.post("/ai/draft", json={"consent_id": cid, "brief": {"approved_facts": [canary]}}, headers=h)
    with app.state.db.engine.connect() as conn:
        tables = [r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))]
        for t in tables:
            for row in conn.execute(text(f'SELECT * FROM "{t}"')):
                assert canary not in json.dumps([str(v) for v in row]), t


def test_admin_isolation_report(client):
    h = admin_login(client)
    rep = client.get("/admin/isolation", headers=h).json()
    assert rep["case_endpoints"] is False
    assert rep["content_columns"] == []
    assert not any(t.startswith("local_") for t in rep["tables"])
    assert client.get("/cases", headers=h).status_code == 404
