from __future__ import annotations

from sqlalchemy.orm import Session

from .models import AdminAuditLog, SecurityEvent


def security_event(db: Session, kind: str, user_id: str | None = None, detail: str | None = None) -> None:
    db.add(SecurityEvent(kind=kind, user_id=user_id, detail=(detail or "")[:300] or None))


def admin_audit(db: Session, admin_id: str, action: str, target: str | None = None, **detail) -> None:
    db.add(AdminAuditLog(admin_id=admin_id, action=action, target=target, detail=detail))
