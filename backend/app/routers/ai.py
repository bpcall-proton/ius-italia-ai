"""IUS AI Orchestrator: consensi, budget, streaming SSE degli step reali."""

from __future__ import annotations

import json
import uuid
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import billing
from ..ai.legal_sources import validate_citations
from ..ai.providers import OpenAICompatibleProvider, ProviderUnavailable, SimulationProvider
from ..deps import Principal, get_db, require_firm_user
from ..models import AIConsentRecord, AIModel, AIUsageRecord, utcnow

router = APIRouter(prefix="/ai", tags=["ai"])

TASK_PROVIDERS = {
    "analyze": ("simulation", "openai", "ollama", "custom"),
    "draft": ("simulation", "deepseek", "openai", "ollama", "custom"),
}


def is_local_url(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return host in ("127.0.0.1", "localhost", "::1")


def ollama_models(url: str) -> list[str] | None:
    try:
        r = httpx.get(f"{url.rstrip('/')}/api/tags", timeout=1.5)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return None


MAX_TOKENS = {"analyze": 6000, "draft": 4000}


def build_provider(request: Request, db: Session, name: str, task: str):
    s = request.app.state.settings
    row = db.scalar(
        select(AIModel).where(AIModel.provider == name, AIModel.task.in_((task, "any")), AIModel.enabled.is_(True))
    )
    if name == "simulation":
        return SimulationProvider(row.model if row else "ius-regole-v1"), row
    model = row.model if row else ""
    if name == "openai":
        return OpenAICompatibleProvider("openai", "OpenAI (analisi)", s.openai_base_url, s.openai_api_key, model), row
    if name == "deepseek":
        return (
            OpenAICompatibleProvider(
                "deepseek", "DeepSeek (redazione)", s.deepseek_base_url, s.deepseek_api_key, model
            ),
            row,
        )
    if name == "ollama":
        model = model or s.ollama_model
        if not model:
            model = (ollama_models(s.ollama_url) or [""])[0]
        return (
            OpenAICompatibleProvider("ollama", "Ollama (locale)", f"{s.ollama_url.rstrip('/')}/v1", "", model, False),
            row,
        )
    if name == "custom":
        return (
            OpenAICompatibleProvider(
                "custom", s.custom_ai_name, s.custom_ai_url, s.custom_ai_key, model or s.custom_ai_model, False
            ),
            row,
        )
    raise HTTPException(status.HTTP_400_BAD_REQUEST, "Provider sconosciuto")


@router.get("/providers")
def providers(request: Request, p: Principal = Depends(require_firm_user), db: Session = Depends(get_db)) -> list[dict]:
    out = []
    for name, label, tasks in (
        ("simulation", "Motore dimostrativo a regole (SIMULAZIONE)", ["analyze", "draft"]),
        ("openai", "OpenAI — ragionamento giuridico", ["analyze", "draft"]),
        ("deepseek", "DeepSeek — redazione", ["draft"]),
        ("ollama", "Ollama — modello sul tuo computer", ["analyze", "draft"]),
        ("custom", f"{request.app.state.settings.custom_ai_name} — server AI dello studio", ["analyze", "draft"]),
    ):
        prov, row = build_provider(request, db, name, tasks[0] if name != "deepseek" else "draft")
        ready = prov.configured()
        if name == "ollama" and ready:
            ready = ollama_models(request.app.state.settings.ollama_url) is not None
        out.append(
            {
                "name": name,
                "label": label,
                "tasks": tasks,
                "model": prov.model or None,
                "status": "attivo" if ready and (row is None or row.enabled) else "non configurato",
                "external": name != "simulation" and not (name in ("ollama", "custom") and is_local_url(prov.base_url)),
            }
        )
    return out


class ConsentIn(BaseModel):
    provider: str
    operation: str
    data_categories: list[str] = Field(default_factory=list)
    char_count: int = 0
    anonymized: bool = False


@router.post("/consents")
def create_consent(body: ConsentIn, p: Principal = Depends(require_firm_user), db: Session = Depends(get_db)) -> dict:
    if body.operation not in TASK_PROVIDERS or body.provider not in TASK_PROVIDERS[body.operation]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Provider non ammesso per questa operazione")
    rec = AIConsentRecord(
        user_id=p.user.id,
        provider=body.provider,
        operation=body.operation,
        data_categories=body.data_categories[:20],
        char_count=max(0, body.char_count),
        anonymized=body.anonymized,
    )
    db.add(rec)
    db.commit()
    return {"id": rec.id, "created_at": rec.created_at}


@router.post("/consents/{consent_id}/revoke")
def revoke_consent(consent_id: str, p: Principal = Depends(require_firm_user), db: Session = Depends(get_db)) -> dict:
    rec = db.get(AIConsentRecord, consent_id)
    if rec is None or rec.user_id != p.user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Consenso non trovato")
    rec.revoked_at = utcnow()
    db.commit()
    return {"ok": True}


class AnalyzeIn(BaseModel):
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex, max_length=64)
    consent_id: str
    provider: str = "simulation"
    description: str = Field(min_length=10, max_length=60_000)


class DraftIn(BaseModel):
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex, max_length=64)
    consent_id: str
    provider: str = "simulation"
    brief: dict


def _check_consent(db: Session, p: Principal, consent_id: str, provider: str, operation: str) -> None:
    rec = db.get(AIConsentRecord, consent_id)
    if (
        rec is None
        or rec.user_id != p.user.id
        or rec.revoked_at is not None
        or rec.provider != provider
        or rec.operation != operation
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Autorizzazione all'invio mancante o revocata")


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _run(
    request: Request,
    p: Principal,
    db: Session,
    *,
    operation: str,
    provider_name: str,
    request_id: str,
    consent_id: str,
    payload,
    steps: list[str],
) -> StreamingResponse:
    if provider_name not in TASK_PROVIDERS[operation]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Provider non ammesso per questa operazione")
    _check_consent(db, p, consent_id, provider_name, operation)
    provider, model_row = build_provider(request, db, provider_name, operation)
    if not provider.configured():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"{provider_name} non configurato")
    cpk = model_row.credits_per_1k_tokens if model_row else 1
    max_tokens = MAX_TOKENS[operation]
    reservation = billing.reserve(
        db,
        firm_id=p.user.firm_id,
        request_id=request_id,
        credits=billing.credits_for_tokens(max_tokens, cpk),
        max_tokens=max_tokens,
    )
    sub = billing.active_subscription(db, p.user.firm_id)
    user_id, firm_id, sub_id = p.user.id, p.user.firm_id, sub.id
    price = billing.current_price(db, model_row) if model_row else None
    SessionLocal = request.app.state.db.SessionLocal

    async def stream():
        sdb = SessionLocal()
        outcome = "error"
        result = None
        try:
            for i, step in enumerate(steps[:-2]):
                yield _sse("step", {"index": i, "label": step})
            try:
                if operation == "analyze":
                    result = await provider.analyze(payload)
                else:
                    result = await provider.draft(payload)
            except ProviderUnavailable as exc:
                yield _sse("error", {"message": str(exc)})
                return
            yield _sse("step", {"index": len(steps) - 2, "label": steps[-2]})
            data = result.data
            if operation == "analyze":
                allowed = [n["id"] for n in data.get("candidate_norms", [])]
                data.setdefault("citation_check", validate_citations(json.dumps(data, ensure_ascii=False), allowed))
            yield _sse("step", {"index": len(steps) - 1, "label": steps[-1]})
            outcome = "ok"
            yield _sse(
                "result",
                {
                    "request_id": request_id,
                    "provider": provider.name,
                    "model": provider.model,
                    "simulated": result.simulated,
                    "data": data,
                },
            )
        finally:
            usage = result.usage if result else billing.Usage()
            res = sdb.merge(reservation)
            charged = billing.settle(sdb, res, billing.credits_for_tokens(usage.total, cpk) if outcome == "ok" else 0)
            sdb.add(
                AIUsageRecord(
                    request_id=request_id,
                    user_id=user_id,
                    firm_id=firm_id,
                    subscription_id=sub_id,
                    provider=provider.name,
                    model=provider.model,
                    operation=operation,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    cached_tokens=usage.cached_tokens,
                    reasoning_tokens=usage.reasoning_tokens,
                    total_tokens=usage.total,
                    cost_micro=billing.cost_micro(price, usage),
                    cost_currency=price.currency if price else "USD",
                    credits_charged=charged,
                    duration_ms=result.duration_ms if result else 0,
                    outcome=outcome if outcome == "ok" else "error",
                    simulated=result.simulated if result else provider.name == "simulation",
                )
            )
            sdb.commit()
            sdb.close()

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})


ANALYZE_STEPS = [
    "Preparazione quesito",
    "Ricerca fonti",
    "Fonti recuperate",
    "Analisi in generazione",
    "Controllo citazioni",
    "Piano d'azione pronto",
]
DRAFT_STEPS = ["Lettura brief approvato", "Redazione bozza", "Controllo citazioni", "Bozza pronta"]


@router.post("/analyze")
def analyze(
    body: AnalyzeIn, request: Request, p: Principal = Depends(require_firm_user), db: Session = Depends(get_db)
) -> StreamingResponse:
    return _run(
        request,
        p,
        db,
        operation="analyze",
        provider_name=body.provider,
        request_id=body.request_id,
        consent_id=body.consent_id,
        payload=body.description,
        steps=ANALYZE_STEPS,
    )


@router.post("/draft")
def draft(
    body: DraftIn, request: Request, p: Principal = Depends(require_firm_user), db: Session = Depends(get_db)
) -> StreamingResponse:
    return _run(
        request,
        p,
        db,
        operation="draft",
        provider_name=body.provider,
        request_id=body.request_id,
        consent_id=body.consent_id,
        payload=body.brief,
        steps=DRAFT_STEPS,
    )
