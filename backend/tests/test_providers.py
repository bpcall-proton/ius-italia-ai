from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.conftest import login


def _client(tmp_path, **kw):
    s = Settings(
        env="test",
        database_url=f"sqlite:///{tmp_path / 'p.db'}",
        data_dir=tmp_path,
        jwt_secret="test-secret-not-for-production-0123456789",
        ollama_url="http://127.0.0.1:9",
        **kw,
    )
    return TestClient(create_app(s))


def test_ollama_spento_e_mio_ai_locale(tmp_path):
    with _client(tmp_path, custom_ai_url="http://127.0.0.1:9/v1", custom_ai_model="studio-7b") as c:
        h = login(c)
        prov = {p["name"]: p for p in c.get("/ai/providers", headers=h).json()}
        assert prov["ollama"]["status"] == "non configurato"
        assert prov["custom"]["status"] == "attivo"
        assert prov["custom"]["external"] is False
        assert prov["custom"]["model"] == "studio-7b"
        r = c.post(
            "/ai/consents",
            headers=h,
            json={"provider": "custom", "operation": "analyze", "data_categories": ["descrizione"]},
        )
        assert r.status_code == 200, r.text
        cid = r.json()["id"]
        before = c.get("/me", headers=h).json()
        out = c.post(
            "/ai/analyze",
            headers=h,
            json={"consent_id": cid, "provider": "custom", "description": "Caso di prova per server spento"},
        )
        assert "non raggiungibile" in out.text
        after = c.get("/me", headers=h).json()
        assert after["credits"] == before["credits"]


def test_mio_ai_remoto_richiede_consenso_esterno(tmp_path):
    with _client(tmp_path, custom_ai_url="https://ai.studio.example/v1", custom_ai_model="m") as c:
        prov = {p["name"]: p for p in c.get("/ai/providers", headers=login(c)).json()}
        assert prov["custom"]["external"] is True
