"""Crediti, limiti e prenotazione atomica del budget AI."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import (
    AIModel,
    AIModelPrice,
    AIUsageRecord,
    AIUsageReservation,
    CreditLedger,
    CreditWallet,
    Subscription,
)


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


def credits_for_tokens(tokens: int, credits_per_1k: int) -> int:
    if tokens <= 0:
        return 0
    return max(1, math.ceil(tokens * credits_per_1k / 1000))


def current_price(db: Session, model: AIModel) -> AIModelPrice | None:
    now = datetime.now(timezone.utc)
    return db.scalar(
        select(AIModelPrice)
        .where(AIModelPrice.model_id == model.id, AIModelPrice.valid_from <= now)
        .order_by(AIModelPrice.valid_from.desc())
        .limit(1)
    )


def cost_micro(price: AIModelPrice | None, usage: Usage) -> int:
    """Costo in micro-unità di valuta: (token × prezzo per milione) / 1.000.000, arrotondato per eccesso."""
    if price is None:
        return 0
    uncached_in = max(0, usage.input_tokens - usage.cached_tokens)
    raw = (
        uncached_in * price.input_per_mtok_micro
        + usage.cached_tokens * price.cached_per_mtok_micro
        + usage.output_tokens * price.output_per_mtok_micro
    )
    return math.ceil(raw / 1_000_000)


def active_subscription(db: Session, firm_id: str) -> Subscription:
    sub = db.scalar(
        select(Subscription)
        .where(Subscription.firm_id == firm_id, Subscription.status.in_(("trial", "active")))
        .order_by(Subscription.started_at.desc())
        .limit(1)
    )
    if sub is None:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "Nessun abbonamento attivo")
    return sub


def month_tokens(db: Session, firm_id: str) -> int:
    now = datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return int(
        db.scalar(
            select(func.coalesce(func.sum(AIUsageRecord.total_tokens), 0)).where(
                AIUsageRecord.firm_id == firm_id, AIUsageRecord.created_at >= start
            )
        )
        or 0
    )


def wallet_for(db: Session, firm_id: str) -> CreditWallet:
    w = db.scalar(select(CreditWallet).where(CreditWallet.firm_id == firm_id))
    if w is None:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "Portafoglio crediti non trovato")
    return w


def reserve(db: Session, *, firm_id: str, request_id: str, credits: int, max_tokens: int) -> AIUsageReservation:
    sub = active_subscription(db, firm_id)
    limit = sub.plan_version.monthly_token_limit
    if month_tokens(db, firm_id) + max_tokens > limit:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Limite mensile di token del piano raggiunto")
    wallet = wallet_for(db, firm_id)
    if db.scalar(select(AIUsageReservation).where(AIUsageReservation.request_id == request_id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Richiesta già ricevuta (id duplicato)")
    res = db.execute(
        update(CreditWallet)
        .where(CreditWallet.id == wallet.id, CreditWallet.balance >= credits)
        .values(balance=CreditWallet.balance - credits, reserved=CreditWallet.reserved + credits)
    )
    if res.rowcount != 1:
        db.rollback()
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "Crediti insufficienti per questa richiesta")
    reservation = AIUsageReservation(request_id=request_id, wallet_id=wallet.id, credits=credits)
    db.add(reservation)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Richiesta già ricevuta (id duplicato)") from None
    return reservation


def settle(db: Session, reservation: AIUsageReservation, charged: int) -> int:
    """Addebita il consumo effettivo (mai oltre la riserva) e rilascia il residuo."""
    if reservation.status != "reserved":
        return 0
    charged = max(0, min(charged, reservation.credits))
    refund = reservation.credits - charged
    db.execute(
        update(CreditWallet)
        .where(CreditWallet.id == reservation.wallet_id)
        .values(balance=CreditWallet.balance + refund, reserved=CreditWallet.reserved - reservation.credits)
    )
    if charged:
        db.add(
            CreditLedger(
                wallet_id=reservation.wallet_id,
                delta=-charged,
                reason="ai_usage",
                idempotency_key=f"charge:{reservation.request_id}",
            )
        )
    reservation.status = "settled" if charged else "released"
    db.add(reservation)
    db.commit()
    return charged


def release(db: Session, reservation: AIUsageReservation) -> None:
    settle(db, reservation, 0)


def grant_credits(db: Session, *, firm_id: str, amount: int, reason: str, key: str, by: str | None) -> bool:
    wallet = wallet_for(db, firm_id)
    if db.scalar(select(CreditLedger).where(CreditLedger.idempotency_key == key)):
        return False
    db.add(CreditLedger(wallet_id=wallet.id, delta=amount, reason=reason, idempotency_key=key, created_by=by))
    db.execute(update(CreditWallet).where(CreditWallet.id == wallet.id).values(balance=CreditWallet.balance + amount))
    db.commit()
    return True
