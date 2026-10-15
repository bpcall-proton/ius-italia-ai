from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import jwt
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def make_token(secret: str, *, sub: str, kind: str, minutes: int, **claims) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": sub, "typ": kind, "iat": now, "exp": now + timedelta(minutes=minutes), **claims}
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def read_token(secret: str, token: str, kind: str) -> dict | None:
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != kind:
        return None
    return payload


def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="IUS Italia AI Admin")


def verify_totp(secret: str, code: str) -> bool:
    code = (code or "").replace(" ", "")
    return bool(code) and pyotp.TOTP(secret).verify(code, valid_window=1)


class LoginThrottle:
    """Limite tentativi di accesso falliti per email (in memoria, per singolo processo)."""

    def __init__(self, max_failures: int = 5, window_s: int = 900) -> None:
        self.max_failures = max_failures
        self.window_s = window_s
        self._fails: dict[str, deque[float]] = defaultdict(deque)

    def _trim(self, key: str) -> deque[float]:
        q = self._fails[key]
        cutoff = time.monotonic() - self.window_s
        while q and q[0] < cutoff:
            q.popleft()
        return q

    def blocked(self, key: str) -> bool:
        return len(self._trim(key)) >= self.max_failures

    def fail(self, key: str) -> None:
        self._trim(key).append(time.monotonic())

    def reset(self, key: str) -> None:
        self._fails.pop(key, None)
