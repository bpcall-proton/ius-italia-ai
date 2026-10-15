"""Portale admin proprietario: dati commerciali aggregati, MAI contenuti dei fascicoli."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, inspect, or_, select
from sqlalchemy.orm import Session

from .. import billing
from ..audit import admin_audit
from ..deps import Principal, get_db, require_admin, require_admin_write
from ..models import (
    AdminAuditLog,
    AIModel,
    AIModelPrice,
    AIUsageRecord,
    CreditWallet,
    LawFirm,
    PlanVersion,
    Role,
    SecurityEvent,
    Subscription,
    SubscriptionPlan,
    User,
    utcnow,
)
from .account import plan_version_dict

router = APIRouter(prefix="/admin", tags=["admin"])


def _firm_usage(db: Session) -> dict[str, dict]:
    rows = db.execute(
        select(
            AIUsageRecord.firm_id,
            func.sum(AIUsageRecord.total_tokens),
            func.sum(AIUsageRecord.cost_micro),
            func.sum(AIUsageRecord.credits_charged),
            func.count(),
        ).group_by(AIUsageRecord.firm_id)
    ).all()
    return {
        r[0]: {"tokens": int(r[1] or 0), "cost_micro": int(r[2] or 0), "credits": int(r[3] or 0), "requests": r[4]}
        for r in rows
    }


def _current_sub(db: Session, firm_id: str) -> Subscription | None:
    return db.scalar(
        select(Subscription).where(Subscription.firm_id == firm_id).order_by(Subscription.started_at.desc()).limit(1)
    )


@router.get("/dashboard")
def dashboard(p: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    lawyers = db.scalars(select(User).where(User.role.in_(Role.FIRM))).all()
    subs = [s for s in (_current_sub(db, f.id) for f in db.scalars(select(LawFirm)).all()) if s]
    paying = [s for s in subs if s.status == "active"]
    mrr = sum(s.plan_version.price_month_cents for s in paying)
    usage = db.execute(
        select(
            AIUsageRecord.simulated,
            func.sum(AIUsageRecord.total_tokens),
            func.sum(AIUsageRecord.cost_micro),
            func.count(),
        ).group_by(AIUsageRecord.simulated)
    ).all()
    return {
        "registered": len(lawyers),
        "active": sum(1 for u in lawyers if u.status == "active"),
        "suspended": sum(1 for u in lawyers if u.status == "suspended"),
        "firms": len(subs),
        "paying": len(paying),
        "trials": sum(1 for s in subs if s.status == "trial"),
        "mrr_cents": mrr,
        "arr_cents": mrr * 12,
        "mrr_note": "MRR teorico dai listini degli abbonamenti attivi: i pagamenti reali non sono ancora integrati.",
        "ai_usage": [
            {"simulated": bool(r[0]), "tokens": int(r[1] or 0), "cost_micro": int(r[2] or 0), "requests": r[3]}
            for r in usage
        ],
    }


@router.get("/lawyers")
def lawyers(
    q: str = "", status_filter: str = "", p: Principal = Depends(require_admin), db: Session = Depends(get_db)
) -> list[dict]:
    stmt = select(User).where(User.role.in_(Role.FIRM))
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(User.email).like(like),
                func.lower(User.last_name).like(like),
                func.lower(User.first_name).like(like),
            )
        )
    if status_filter:
        stmt = stmt.where(User.status == status_filter)
    usage = _firm_usage(db)
    out = []
    for u in db.scalars(stmt.order_by(User.created_at)).all():
        sub = _current_sub(db, u.firm_id) if u.firm_id else None
        wallet = db.scalar(select(CreditWallet).where(CreditWallet.firm_id == u.firm_id)) if u.firm_id else None
        fu = usage.get(u.firm_id or "", {})
        out.append(
            {
                "id": u.id,
                "first_name": u.first_name,
                "last_name": u.last_name,
                "email": u.email,
                "role": u.role,
                "firm": {"id": u.firm.id, "name": u.firm.name, "vat": u.firm.vat_number, "country": u.firm.country}
                if u.firm
                else None,
                "registered_at": u.created_at,
                "last_login_at": u.last_login_at,
                "plan": sub.plan_version.plan.name if sub else None,
                "subscription_status": sub.status if sub else None,
                "status": u.status,
                "credits": wallet.balance if wallet else 0,
                "tokens": fu.get("tokens", 0),
                "ai_cost_micro": fu.get("cost_micro", 0),
            }
        )
    return out


class StatusIn(BaseModel):
    status: str = Field(pattern="^(active|suspended)$")


@router.post("/lawyers/{user_id}/status")
def set_status(
    user_id: str, body: StatusIn, p: Principal = Depends(require_admin_write), db: Session = Depends(get_db)
) -> dict:
    u = db.get(User, user_id)
    if u is None or u.role not in Role.FIRM:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Avvocato non trovato")
    u.status = body.status
    admin_audit(db, p.user.id, "lawyer_status", u.id, status=body.status)
    db.commit()
    return {"ok": True, "status": u.status}


class CreditsIn(BaseModel):
    amount: int = Field(gt=0, le=100_000)
    reason: str = Field(default="bonus", max_length=32)
    idempotency_key: str = Field(min_length=8, max_length=64)


@router.post("/firms/{firm_id}/credits")
def add_credits(
    firm_id: str, body: CreditsIn, p: Principal = Depends(require_admin_write), db: Session = Depends(get_db)
) -> dict:
    if db.get(LawFirm, firm_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Studio non trovato")
    applied = billing.grant_credits(
        db, firm_id=firm_id, amount=body.amount, reason=body.reason, key=f"admin:{body.idempotency_key}", by=p.user.id
    )
    if applied:
        admin_audit(db, p.user.id, "credits_bonus", firm_id, amount=body.amount)
        db.commit()
    return {"applied": applied, "balance": billing.wallet_for(db, firm_id).balance}


@router.get("/plans")
def admin_plans(p: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> list[dict]:
    out = []
    for plan in db.scalars(select(SubscriptionPlan)).all():
        counts = dict(
            db.execute(
                select(Subscription.plan_version_id, func.count())
                .join(PlanVersion, PlanVersion.id == Subscription.plan_version_id)
                .where(PlanVersion.plan_id == plan.id)
                .group_by(Subscription.plan_version_id)
            ).all()
        )
        out.append(
            {
                "code": plan.code,
                "name": plan.name,
                "active": plan.active,
                "versions": [{**plan_version_dict(v), "subscriptions": counts.get(v.id, 0)} for v in plan.versions],
            }
        )
    out.sort(key=lambda x: x["versions"][-1]["price_month_cents"] if x["versions"] else 0)
    return out


class PlanVersionIn(BaseModel):
    price_month_cents: int = Field(ge=0, le=10_000_000)
    price_year_cents: int | None = Field(default=None, ge=0, le=100_000_000)
    monthly_credits: int = Field(ge=0, le=10_000_000)
    monthly_token_limit: int = Field(ge=0, le=10_000_000_000)
    note: str | None = Field(default=None, max_length=300)


@router.post("/plans/{code}/versions")
def new_plan_version(
    code: str, body: PlanVersionIn, p: Principal = Depends(require_admin_write), db: Session = Depends(get_db)
) -> dict:
    plan = db.scalar(select(SubscriptionPlan).where(SubscriptionPlan.code == code))
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Piano non trovato")
    last = plan.versions[-1] if plan.versions else None
    v = PlanVersion(
        plan_id=plan.id,
        version=(last.version + 1) if last else 1,
        price_month_cents=body.price_month_cents,
        price_year_cents=body.price_year_cents,
        monthly_credits=body.monthly_credits,
        monthly_token_limit=body.monthly_token_limit,
        features=last.features if last else {},
        created_by=p.user.id,
        note=body.note,
    )
    db.add(v)
    admin_audit(
        db,
        p.user.id,
        "plan_version_created",
        code,
        version=v.version,
        price_month_cents=v.price_month_cents,
        previous_price_cents=last.price_month_cents if last else None,
    )
    db.commit()
    return plan_version_dict(v)


@router.get("/ai-usage")
def ai_usage(limit: int = 200, p: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(AIUsageRecord).order_by(AIUsageRecord.created_at.desc()).limit(min(limit, 1000))).all()
    firms = {f.id: f.name for f in db.scalars(select(LawFirm)).all()}
    users = {u.id: u.email for u in db.scalars(select(User)).all()}
    by_model = db.execute(
        select(
            AIUsageRecord.provider,
            AIUsageRecord.model,
            AIUsageRecord.simulated,
            func.sum(AIUsageRecord.total_tokens),
            func.sum(AIUsageRecord.cost_micro),
            func.count(),
        ).group_by(AIUsageRecord.provider, AIUsageRecord.model, AIUsageRecord.simulated)
    ).all()
    return {
        "records": [
            {
                "request_id": r.request_id,
                "created_at": r.created_at,
                "user": users.get(r.user_id),
                "firm": firms.get(r.firm_id),
                "provider": r.provider,
                "model": r.model,
                "operation": r.operation,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "cached_tokens": r.cached_tokens,
                "reasoning_tokens": r.reasoning_tokens,
                "total_tokens": r.total_tokens,
                "cost_micro": r.cost_micro,
                "currency": r.cost_currency,
                "credits": r.credits_charged,
                "duration_ms": r.duration_ms,
                "outcome": r.outcome,
                "simulated": r.simulated,
            }
            for r in rows
        ],
        "by_model": [
            {
                "provider": b[0],
                "model": b[1],
                "simulated": bool(b[2]),
                "tokens": int(b[3] or 0),
                "cost_micro": int(b[4] or 0),
                "requests": b[5],
            }
            for b in by_model
        ],
    }


@router.get("/models")
def models(p: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> list[dict]:
    out = []
    for m in db.scalars(select(AIModel).order_by(AIModel.provider)).all():
        price = billing.current_price(db, m)
        out.append(
            {
                "id": m.id,
                "provider": m.provider,
                "model": m.model,
                "task": m.task,
                "enabled": m.enabled,
                "credits_per_1k_tokens": m.credits_per_1k_tokens,
                "price": None
                if price is None
                else {
                    "currency": price.currency,
                    "input_per_mtok_micro": price.input_per_mtok_micro,
                    "output_per_mtok_micro": price.output_per_mtok_micro,
                    "cached_per_mtok_micro": price.cached_per_mtok_micro,
                    "valid_from": price.valid_from,
                    "source_note": price.source_note,
                },
            }
        )
    return out


class ModelIn(BaseModel):
    provider: str = Field(pattern="^(openai|deepseek|ollama|simulation)$")
    model: str = Field(min_length=1, max_length=100)
    task: str = Field(pattern="^(analyze|draft|any)$")
    enabled: bool = True
    credits_per_1k_tokens: int = Field(default=1, ge=0, le=1000)


@router.post("/models")
def upsert_model(body: ModelIn, p: Principal = Depends(require_admin_write), db: Session = Depends(get_db)) -> dict:
    m = db.scalar(select(AIModel).where(AIModel.provider == body.provider, AIModel.model == body.model))
    if m is None:
        for other in db.scalars(select(AIModel).where(AIModel.provider == body.provider, AIModel.task == body.task)):
            if body.enabled:
                other.enabled = False
        m = AIModel(provider=body.provider, model=body.model)
        db.add(m)
    m.task, m.enabled, m.credits_per_1k_tokens = body.task, body.enabled, body.credits_per_1k_tokens
    admin_audit(db, p.user.id, "model_upsert", f"{body.provider}/{body.model}", enabled=body.enabled)
    db.commit()
    return {"id": m.id}


class PriceIn(BaseModel):
    currency: str = Field(default="USD", pattern="^[A-Z]{3}$")
    input_per_mtok_micro: int = Field(ge=0)
    output_per_mtok_micro: int = Field(ge=0)
    cached_per_mtok_micro: int = Field(default=0, ge=0)
    source_note: str | None = Field(default=None, max_length=300)


@router.post("/models/{model_id}/prices")
def add_price(
    model_id: str, body: PriceIn, p: Principal = Depends(require_admin_write), db: Session = Depends(get_db)
) -> dict:
    m = db.get(AIModel, model_id)
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Modello non trovato")
    price = AIModelPrice(model_id=m.id, valid_from=utcnow() - timedelta(seconds=1), **body.model_dump())
    db.add(price)
    admin_audit(db, p.user.id, "model_price_added", f"{m.provider}/{m.model}", **body.model_dump())
    db.commit()
    return {"id": price.id}


@router.get("/audit")
def audit(p: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> list[dict]:
    users = {u.id: u.email for u in db.scalars(select(User)).all()}
    rows = db.scalars(select(AdminAuditLog).order_by(AdminAuditLog.created_at.desc()).limit(300)).all()
    return [
        {"at": r.created_at, "admin": users.get(r.admin_id), "action": r.action, "target": r.target, "detail": r.detail}
        for r in rows
    ]


@router.get("/security-events")
def security_events(p: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> list[dict]:
    users = {u.id: u.email for u in db.scalars(select(User)).all()}
    rows = db.scalars(select(SecurityEvent).order_by(SecurityEvent.created_at.desc()).limit(300)).all()
    return [{"at": r.created_at, "user": users.get(r.user_id), "kind": r.kind} for r in rows]


@router.get("/isolation")
def isolation(request: Request, p: Principal = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    """Prova verificabile: elenco completo di tabelle e colonne del database commerciale."""
    insp = inspect(db.get_bind())
    tables = {t: [c["name"] for c in insp.get_columns(t)] for t in insp.get_table_names() if t != "alembic_version"}
    content_like = [
        f"{t}.{c}"
        for t, cols in tables.items()
        for c in cols
        if any(k in c for k in ("content", "text", "body", "prompt", "document", "html", "description"))
    ]
    return {
        "tables": tables,
        "content_columns": content_like,
        "case_endpoints": False,
        "explanation": (
            "Fascicoli, documenti e bozze esistono solo nell'archivio cifrato sul PC dell'avvocato "
            "(AES-256-GCM, chiave per fascicolo protetta dalla passphrase locale). Il server non riceve le chiavi, "
            "non ha API per i fascicoli e non registra il testo delle richieste AI."
        ),
    }
