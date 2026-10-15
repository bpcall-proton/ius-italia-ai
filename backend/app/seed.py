"""Dati di prova (nessun dato reale). Gli account demo vengono creati solo se IUS_SEED_DEMO=true."""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    AIModel,
    AIModelPrice,
    AIUsageRecord,
    CreditWallet,
    LawFirm,
    PlanVersion,
    Role,
    Subscription,
    SubscriptionPlan,
    User,
    utcnow,
)
from .security import hash_password

DEMO_LAWYER = ("avvocato@demo.ius", "Demo-Avvocato-2026")
DEMO_ADMIN = ("admin@demo.ius", "Demo-Admin-2026")

PLANS = [
    ("BASE", "Base", 1900, 100, 200_000),
    ("PRO", "Pro", 3900, 300, 600_000),
    ("PREMIUM", "Premium", 7900, 800, 1_600_000),
]


def seed_catalog(db: Session) -> None:
    for code, name, price, credits, tokens in PLANS:
        if db.scalar(select(SubscriptionPlan).where(SubscriptionPlan.code == code)):
            continue
        plan = SubscriptionPlan(code=code, name=name)
        db.add(plan)
        db.flush()
        db.add(
            PlanVersion(
                plan_id=plan.id,
                version=1,
                price_month_cents=price,
                price_year_cents=price * 10,
                monthly_credits=credits,
                monthly_token_limit=tokens,
                features={"analisi": True, "redazione": True},
                note="Listino iniziale",
            )
        )
    if not db.scalar(select(AIModel).where(AIModel.provider == "simulation")):
        sim = AIModel(provider="simulation", model="ius-regole-v1", task="any", credits_per_1k_tokens=1)
        db.add(sim)
        db.flush()
        db.add(
            AIModelPrice(
                model_id=sim.id,
                currency="USD",
                input_per_mtok_micro=0,
                output_per_mtok_micro=0,
                valid_from=utcnow() - timedelta(days=1),
                source_note="Simulazione: nessun costo API",
            )
        )
    db.commit()


def _plan_version(db: Session, code: str) -> PlanVersion:
    plan = db.scalar(select(SubscriptionPlan).where(SubscriptionPlan.code == code))
    return plan.versions[-1]


def create_firm_user(
    db: Session,
    *,
    email: str,
    password: str,
    first: str,
    last: str,
    firm_name: str,
    plan_code: str = "PRO",
    status: str = "trial",
) -> User:
    firm = LawFirm(name=firm_name, country="IT")
    db.add(firm)
    db.flush()
    pv = _plan_version(db, plan_code)
    db.add(
        Subscription(
            firm_id=firm.id,
            plan_version_id=pv.id,
            status=status,
            trial_ends_at=utcnow() + timedelta(days=14) if status == "trial" else None,
        )
    )
    db.add(CreditWallet(firm_id=firm.id, balance=pv.monthly_credits))
    user = User(
        email=email.lower(),
        password_hash=hash_password(password),
        first_name=first,
        last_name=last,
        role=Role.FIRM_OWNER,
        firm_id=firm.id,
    )
    db.add(user)
    db.commit()
    return user


def seed_demo(db: Session) -> None:
    if db.scalar(select(User).where(User.email == DEMO_LAWYER[0])):
        return
    lawyer = create_firm_user(
        db,
        email=DEMO_LAWYER[0],
        password=DEMO_LAWYER[1],
        first="Mario",
        last="Rossi",
        firm_name="Studio Legale Demo Rossi",
        plan_code="PRO",
    )
    for i, (email, first, last, firm, code, status) in enumerate(
        [
            ("giulia.bianchi@demo.ius", "Giulia", "Bianchi", "Studio Demo Bianchi", "BASE", "active"),
            ("luca.verdi@demo.ius", "Luca", "Verdi", "Studio Demo Verdi & Associati", "PREMIUM", "active"),
        ]
    ):
        u = create_firm_user(
            db,
            email=email,
            password=uuid.uuid4().hex,
            first=first,
            last=last,
            firm_name=firm,
            plan_code=code,
            status=status,
        )
        for j in range(3 + i):
            tokens_in, tokens_out = 1800 + 400 * j, 900 + 150 * j
            db.add(
                AIUsageRecord(
                    request_id=f"demo-{u.id[:8]}-{j}",
                    user_id=u.id,
                    firm_id=u.firm_id,
                    provider="simulation",
                    model="ius-regole-v1",
                    operation="analyze" if j % 2 == 0 else "draft",
                    input_tokens=tokens_in,
                    output_tokens=tokens_out,
                    total_tokens=tokens_in + tokens_out,
                    cost_micro=0,
                    credits_charged=3,
                    duration_ms=40,
                    outcome="ok",
                    simulated=True,
                )
            )
    db.add(
        User(
            email=DEMO_ADMIN[0],
            password_hash=hash_password(DEMO_ADMIN[1]),
            first_name="Admin",
            last_name="IUS",
            role=Role.SUPER_ADMIN,
        )
    )
    db.commit()
    del lawyer
