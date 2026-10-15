from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import security_event
from ..deps import Principal, current_principal, get_db
from ..models import AuthSession, Role, User, utcnow
from ..security import make_token, new_totp_secret, read_token, totp_uri, verify_password, verify_totp

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: EmailStr
    password: str
    device: str | None = None


class MfaIn(BaseModel):
    challenge: str
    code: str


def _issue(request: Request, db: Session, user: User, *, mfa: bool, device: str | None) -> dict:
    minutes = request.app.state.settings.access_token_minutes
    sess = AuthSession(
        user_id=user.id,
        expires_at=utcnow() + timedelta(minutes=minutes),
        mfa_verified=mfa,
        device_label=(device or "")[:120] or None,
    )
    db.add(sess)
    user.last_login_at = utcnow()
    db.flush()
    token = make_token(request.app.state.jwt_secret, sub=user.id, kind="access", minutes=minutes, sid=sess.id)
    security_event(db, "login_ok", user.id, device)
    db.commit()
    return {"access_token": token, "token_type": "bearer", "expires_in": minutes * 60, "role": user.role}


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)) -> dict:
    throttle = request.app.state.throttle
    key = body.email.lower()
    if throttle.blocked(key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Troppi tentativi. Riprova tra 15 minuti.")
    user = db.scalar(select(User).where(User.email == key))
    if user is None or not verify_password(user.password_hash, body.password):
        throttle.fail(key)
        security_event(db, "login_failed", user.id if user else None)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email o password non corretti")
    if user.status != "active":
        security_event(db, "login_blocked_suspended", user.id)
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account sospeso. Contatta l'assistenza.")
    throttle.reset(key)

    if user.role in Role.ADMINS:
        challenge = make_token(request.app.state.jwt_secret, sub=user.id, kind="mfa", minutes=5)
        if not user.mfa_enabled:
            if not user.totp_secret:
                user.totp_secret = new_totp_secret()
                db.commit()
            return {
                "mfa_setup_required": True,
                "challenge": challenge,
                "otpauth_uri": totp_uri(user.totp_secret, user.email),
                "secret": user.totp_secret,
            }
        return {"mfa_required": True, "challenge": challenge}
    return _issue(request, db, user, mfa=False, device=body.device)


@router.post("/mfa")
def mfa(body: MfaIn, request: Request, db: Session = Depends(get_db)) -> dict:
    payload = read_token(request.app.state.jwt_secret, body.challenge, "mfa")
    if not payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Verifica scaduta, ripeti l'accesso")
    user = db.get(User, payload["sub"])
    if user is None or not user.totp_secret or user.status != "active":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Verifica non valida")
    if not verify_totp(user.totp_secret, body.code):
        security_event(db, "mfa_failed", user.id)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Codice MFA non valido")
    if not user.mfa_enabled:
        user.mfa_enabled = True
        security_event(db, "mfa_enrolled", user.id)
    return _issue(request, db, user, mfa=True, device=None)


@router.post("/logout")
def logout(p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    sess = db.get(AuthSession, p.session.id)
    sess.revoked_at = utcnow()
    security_event(db, "logout", p.user.id)
    db.commit()
    return {"ok": True}


@router.get("/sessions")
def sessions(p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(
        select(AuthSession)
        .where(AuthSession.user_id == p.user.id, AuthSession.revoked_at.is_(None))
        .order_by(AuthSession.created_at.desc())
    ).all()
    now = datetime.now(timezone.utc)
    return [
        {
            "id": s.id,
            "device": s.device_label,
            "created_at": s.created_at,
            "current": s.id == p.session.id,
        }
        for s in rows
        if (s.expires_at if s.expires_at.tzinfo else s.expires_at.replace(tzinfo=timezone.utc)) > now
    ]


@router.post("/sessions/{session_id}/revoke")
def revoke(session_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    sess = db.get(AuthSession, session_id)
    if sess is None or sess.user_id != p.user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sessione non trovata")
    sess.revoked_at = utcnow()
    security_event(db, "session_revoked", p.user.id)
    db.commit()
    return {"ok": True}
