from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.seed import DEMO_ADMIN, DEMO_LAWYER


def _app(tmp_path, **kw):
    return TestClient(
        create_app(
            Settings(
                env="test",
                database_url=f"sqlite:///{tmp_path / 'r.db'}",
                data_dir=tmp_path,
                jwt_secret="test-secret-not-for-production-0123456789",
                **kw,
            )
        )
    )


def _login(c, email, pw):
    return c.post("/auth/login", json={"email": email, "password": pw})


def test_password_cambiata_su_render_vale_al_riavvio(tmp_path):
    with _app(tmp_path, demo_admin_password="Vecchia-Admin-2026", demo_lawyer_password="Vecchia-Avv-2026") as c:
        r = _login(c, DEMO_ADMIN[0], "Vecchia-Admin-2026")
        assert r.status_code == 200 and r.json().get("mfa_setup_required")
        c.post("/auth/mfa", json={"challenge": r.json()["challenge"], "code": "000000"})
    with _app(
        tmp_path, demo_admin_password="Nuova-Admin-2026", demo_lawyer_password="Nuova-Avv-2026", admin_reset_mfa=True
    ) as c:
        assert _login(c, DEMO_ADMIN[0], "Vecchia-Admin-2026").status_code == 401
        r = _login(c, DEMO_ADMIN[0], "Nuova-Admin-2026")
        assert r.status_code == 200 and r.json().get("mfa_setup_required")
        assert _login(c, DEMO_LAWYER[0], "Nuova-Avv-2026").status_code == 200
        assert _login(c, DEMO_LAWYER[0], DEMO_LAWYER[1]).status_code == 401
