from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import billing
from ..deps import Principal, current_principal, get_db, require_firm_user
from ..models import CreditTopupRequest, PlanVersion, Role, SubscriptionPlan

router = APIRouter(tags=["account"])


def plan_version_dict(v: PlanVersion) -> dict:
    return {
        "id": v.id,
        "version": v.version,
        "price_month_cents": v.price_month_cents,
        "price_year_cents": v.price_year_cents,
        "currency": v.currency,
        "monthly_credits": v.monthly_credits,
        "monthly_token_limit": v.monthly_token_limit,
        "features": v.features,
        "valid_from": v.valid_from,
        "note": v.note,
    }


@router.get("/plans")
def plans(db: Session = Depends(get_db)) -> list[dict]:
    out = []
    for plan in db.scalars(select(SubscriptionPlan).where(SubscriptionPlan.active.is_(True))).all():
        if plan.versions:
            out.append({"code": plan.code, "name": plan.name, "current": plan_version_dict(plan.versions[-1])})
    out.sort(key=lambda p: p["current"]["price_month_cents"])
    return out


@router.get("/me")
def me(p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    u = p.user
    data = {
        "id": u.id,
        "email": u.email,
        "first_name": u.first_name,
        "last_name": u.last_name,
        "role": u.role,
        "is_admin": u.role in Role.ADMINS,
        "firm": None,
        "subscription": None,
        "credits": None,
        "usage": None,
    }
    if u.firm_id:
        data["firm"] = {"id": u.firm.id, "name": u.firm.name}
        sub = billing.active_subscription(db, u.firm_id)
        pv = sub.plan_version
        data["subscription"] = {
            "status": sub.status,
            "plan": pv.plan.name,
            "plan_code": pv.plan.code,
            "trial_ends_at": sub.trial_ends_at,
            "version": plan_version_dict(pv),
        }
        w = billing.wallet_for(db, u.firm_id)
        data["credits"] = {"balance": w.balance, "reserved": w.reserved, "monthly": pv.monthly_credits}
        used = billing.month_tokens(db, u.firm_id)
        pct = round(100 * used / pv.monthly_token_limit, 1) if pv.monthly_token_limit else 0
        data["usage"] = {
            "month_tokens": used,
            "month_token_limit": pv.monthly_token_limit,
            "percent": pct,
            "warning": next((lvl for lvl in (100, 90, 70) if pct >= lvl), None),
        }
    return data


def topup_dict(t: CreditTopupRequest) -> dict:
    return {
        "id": t.id,
        "credits": t.credits,
        "status": t.status,
        "created_at": t.created_at,
        "decided_at": t.decided_at,
    }


class TopupIn(BaseModel):
    credits: int = Field(ge=100, le=100_000)


@router.post("/credits/topups")
def request_topup(body: TopupIn, p: Principal = Depends(require_firm_user), db: Session = Depends(get_db)) -> dict:
    pending = db.scalar(
        select(CreditTopupRequest).where(
            CreditTopupRequest.firm_id == p.user.firm_id, CreditTopupRequest.status == "in_attesa"
        )
    )
    if pending:
        raise HTTPException(status.HTTP_409_CONFLICT, "C'è già una richiesta di ricarica in attesa")
    t = CreditTopupRequest(firm_id=p.user.firm_id, user_id=p.user.id, credits=body.credits)
    db.add(t)
    db.commit()
    return topup_dict(t)


@router.get("/credits/topups")
def my_topups(p: Principal = Depends(require_firm_user), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(
        select(CreditTopupRequest)
        .where(CreditTopupRequest.firm_id == p.user.firm_id)
        .order_by(CreditTopupRequest.created_at.desc())
        .limit(20)
    )
    return [topup_dict(t) for t in rows]
