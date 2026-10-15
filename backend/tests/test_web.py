from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_versione_online_serve_app_e_password_demo_configurabili(tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html>IUS web</html>")
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{tmp_path / 'web.db'}",
        data_dir=tmp_path,
        jwt_secret="test-secret-not-for-production-0123456789",
        web_dir=str(web),
        demo_admin_password="Admin-Online-Segreta-1",
    )
    with TestClient(create_app(settings)) as c:
        assert "IUS web" in c.get("/").text
        assert c.get("/health").json()["ok"] is True
        r = c.post("/auth/login", json={"email": "admin@demo.ius", "password": "Demo-Admin-2026"})
        assert r.status_code == 401
        r = c.post("/auth/login", json={"email": "admin@demo.ius", "password": "Admin-Online-Segreta-1"})
        assert r.status_code == 200
