from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .models import AuthSession, Role, User
from .security import read_token

bearer = HTTPBearer(auto_error=False)


def get_db(request: Request) -> Iterator[Session]:
    yield from request.app.state.db.session()


@dataclass
class Principal:
    user: User
    session: AuthSession

    @property
    def is_admin(self) -> bool:
        return self.user.role in Role.ADMINS


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def current_principal(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> Principal:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessione non valida o scaduta")
    if creds is None:
        raise unauthorized
    payload = read_token(request.app.state.jwt_secret, creds.credentials, "access")
    if not payload:
        raise unauthorized
    sess = db.get(AuthSession, payload.get("sid"))
    if sess is None or sess.revoked_at is not None or _aware(sess.expires_at) < datetime.now(timezone.utc):
        raise unauthorized
    user = db.get(User, payload["sub"])
    if user is None or user.id != sess.user_id or user.status != "active":
        raise unauthorized
    return Principal(user=user, session=sess)


def require_firm_user(p: Principal = Depends(current_principal)) -> Principal:
    if p.user.role not in Role.FIRM or not p.user.firm_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Funzione riservata agli utenti degli studi")
    return p


def require_admin(p: Principal = Depends(current_principal)) -> Principal:
    if not p.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Area riservata agli amministratori")
    if not p.session.mfa_verified:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "MFA obbligatoria per l'area admin")
    return p


def require_admin_write(p: Principal = Depends(require_admin)) -> Principal:
    if p.user.role not in {Role.SUPER_ADMIN, Role.ADMIN_COMMERCIAL}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ruolo non autorizzato a modificare")
    return p
