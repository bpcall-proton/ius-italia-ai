"""Modello dati del backend commerciale.

Il database commerciale NON contiene testi dei fascicoli, documenti, bozze o prompt:
solo identità, abbonamenti, crediti, consumi e audit con metadati minimi.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex


class Role:
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN_COMMERCIAL = "ADMIN_COMMERCIAL"
    ADMIN_TECH = "ADMIN_TECH"
    FIRM_OWNER = "FIRM_OWNER"
    LAWYER = "LAWYER"
    COLLABORATOR = "COLLABORATOR"
    SECRETARY = "SECRETARY"

    ADMINS = frozenset({SUPER_ADMIN, ADMIN_COMMERCIAL, ADMIN_TECH})
    FIRM = frozenset({FIRM_OWNER, LAWYER, COLLABORATOR, SECRETARY})


class LawFirm(Base):
    __tablename__ = "law_firms"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    vat_number: Mapped[str | None] = mapped_column(String(32))
    country: Mapped[str] = mapped_column(String(2), default="IT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    members: Mapped[list[User]] = relationship(back_populates="firm")


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    firm_id: Mapped[str | None] = mapped_column(ForeignKey("law_firms.id"), index=True)
    totp_secret: Mapped[str | None] = mapped_column(String(64))
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    firm: Mapped[LawFirm | None] = relationship(back_populates="members")


class AuthSession(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mfa_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    device_label: Mapped[str | None] = mapped_column(String(120))


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    versions: Mapped[list[PlanVersion]] = relationship(back_populates="plan", order_by="PlanVersion.version")


class PlanVersion(Base):
    """Listino versionato: una modifica di prezzo crea una nuova versione e non tocca le vecchie."""

    __tablename__ = "plan_versions"
    __table_args__ = (
        UniqueConstraint("plan_id", "version"),
        CheckConstraint("price_month_cents >= 0"),
        CheckConstraint("monthly_credits >= 0"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    plan_id: Mapped[str] = mapped_column(ForeignKey("subscription_plans.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    price_month_cents: Mapped[int] = mapped_column(Integer)
    price_year_cents: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    monthly_credits: Mapped[int] = mapped_column(Integer)
    monthly_token_limit: Mapped[int] = mapped_column(Integer)
    features: Mapped[dict] = mapped_column(JSON, default=dict)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str | None] = mapped_column(String(300))

    plan: Mapped[SubscriptionPlan] = relationship(back_populates="versions")


class Subscription(Base):
    __tablename__ = "subscriptions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    firm_id: Mapped[str] = mapped_column(ForeignKey("law_firms.id"), index=True)
    plan_version_id: Mapped[str] = mapped_column(ForeignKey("plan_versions.id"))
    status: Mapped[str] = mapped_column(String(16), default="trial")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    plan_version: Mapped[PlanVersion] = relationship()


class CreditWallet(Base):
    __tablename__ = "credit_wallets"
    __table_args__ = (CheckConstraint("balance >= 0"), CheckConstraint("reserved >= 0"))
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    firm_id: Mapped[str] = mapped_column(ForeignKey("law_firms.id"), unique=True)
    balance: Mapped[int] = mapped_column(Integer, default=0)
    reserved: Mapped[int] = mapped_column(Integer, default=0)


class CreditLedger(Base):
    __tablename__ = "credit_ledger"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    wallet_id: Mapped[str] = mapped_column(ForeignKey("credit_wallets.id"), index=True)
    delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(32))
    idempotency_key: Mapped[str] = mapped_column(String(80), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


class AIModel(Base):
    __tablename__ = "ai_models"
    __table_args__ = (UniqueConstraint("provider", "model"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(100))
    task: Mapped[str] = mapped_column(String(16))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    credits_per_1k_tokens: Mapped[int] = mapped_column(Integer, default=1)


class AIModelPrice(Base):
    """Prezzi API versionati, in micro-unità della valuta per 1 milione di token."""

    __tablename__ = "ai_model_prices"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    model_id: Mapped[str] = mapped_column(ForeignKey("ai_models.id"), index=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    input_per_mtok_micro: Mapped[int] = mapped_column(Integer)
    output_per_mtok_micro: Mapped[int] = mapped_column(Integer)
    cached_per_mtok_micro: Mapped[int] = mapped_column(Integer, default=0)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source_note: Mapped[str | None] = mapped_column(String(300))


class AIUsageReservation(Base):
    __tablename__ = "ai_usage_reservations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    request_id: Mapped[str] = mapped_column(String(64), unique=True)
    wallet_id: Mapped[str] = mapped_column(ForeignKey("credit_wallets.id"), index=True)
    credits: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="reserved")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AIUsageRecord(Base):
    """Registro consumi: solo numeri e metadati, mai il contenuto dei prompt."""

    __tablename__ = "ai_usage_records"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    request_id: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    firm_id: Mapped[str] = mapped_column(ForeignKey("law_firms.id"), index=True)
    subscription_id: Mapped[str | None] = mapped_column(ForeignKey("subscriptions.id"))
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(100))
    operation: Mapped[str] = mapped_column(String(32))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0)
    reasoning_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_micro: Mapped[int] = mapped_column(Integer, default=0)
    cost_currency: Mapped[str] = mapped_column(String(3), default="USD")
    credits_charged: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    outcome: Mapped[str] = mapped_column(String(16))
    simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AIConsentRecord(Base):
    """Autorizzazione all'invio a un provider: categorie di dati, mai il contenuto."""

    __tablename__ = "ai_consent_records"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    operation: Mapped[str] = mapped_column(String(32))
    data_categories: Mapped[list] = mapped_column(JSON, default=list)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    anonymized: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SecurityEvent(Base):
    __tablename__ = "security_events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(48))
    detail: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    admin_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str | None] = mapped_column(String(100))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
