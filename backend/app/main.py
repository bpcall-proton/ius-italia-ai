from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import Settings, get_settings
from .db import Database
from .migrate import upgrade
from .routers import account, admin, ai, auth
from .security import LoginThrottle
from .seed import seed_catalog, seed_demo


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        upgrade(app.state.db.engine)
        with app.state.db.SessionLocal() as db:
            seed_catalog(db)
            if settings.seed_demo:
                seed_demo(db, settings.demo_lawyer_password, settings.demo_admin_password)
        yield

    app = FastAPI(title="IUS Italia AI — Backend", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.db = Database(settings.database_url)
    app.state.jwt_secret = settings.resolved_jwt_secret()
    app.state.throttle = LoginThrottle()
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def no_store(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "version": __version__, "env": settings.env}

    for r in (auth.router, account.router, ai.router, admin.router):
        app.include_router(r)
    if settings.web_dir and (Path(settings.web_dir) / "index.html").is_file():
        app.mount("/", StaticFiles(directory=settings.web_dir, html=True), name="web")
    return app
