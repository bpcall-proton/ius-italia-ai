"""Configurazione del backend IUS Italia AI (solo variabili d'ambiente, nessun segreto nel codice)."""

from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IUS_", env_file=".env", extra="ignore")

    env: str = "demo"
    database_url: str = "sqlite:///./ius-demo.db"
    data_dir: Path = Path(".")
    jwt_secret: str = ""
    access_token_minutes: int = 60
    seed_demo: bool = True
    cors_origins: str = "*"
    web_dir: str = ""
    demo_lawyer_password: str = ""
    demo_admin_password: str = ""

    openai_api_key: str = ""
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    openai_base_url: str = "https://api.openai.com/v1"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = ""
    custom_ai_name: str = "Mio AI"
    custom_ai_url: str = ""
    custom_ai_key: str = ""
    custom_ai_model: str = ""

    def resolved_jwt_secret(self) -> str:
        if self.jwt_secret:
            return self.jwt_secret
        if self.env == "production":
            raise RuntimeError("IUS_JWT_SECRET obbligatorio in produzione")
        path = Path(self.data_dir) / ".ius-jwt-secret"
        if path.exists():
            return path.read_text().strip()
        value = secrets.token_urlsafe(48)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)
        try:
            path.chmod(0o600)
        except OSError:
            pass
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
