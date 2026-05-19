"""
Authentifizierung: Argon2-Passwort-Hashing, JWT-Tokens, zxcvbn-Stärkeprüfung.

Design-Entscheide (aus Architektur V1.4):
  - JWT ausschliesslich im HttpOnly-Cookie
  - Argon2id (sicherer als bcrypt)
  - zxcvbn Score >= 3 verpflichtend
  - Access-Token: 8h, Refresh-Token: 30 Tage
"""
from datetime import datetime, timedelta, timezone
from typing import Any

import zxcvbn as zxcvbn_lib
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from jose import JWTError, jwt

from app.config import settings

# Argon2id mit sicheren Defaults
_ph = PasswordHasher(
    time_cost=2,       # Iterationen
    memory_cost=65536, # 64 MB
    parallelism=2,
    hash_len=32,
    salt_len=16,
)

ALGORITHM = "HS256"
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"


# =============================================================================
# PASSWORT
# =============================================================================

def hash_password(password: str) -> str:
    """Passwort mit Argon2id hashen."""
    return _ph.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Passwort gegen Hash prüfen. False bei falschem Passwort."""
    try:
        return _ph.verify(hashed, plain)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(hashed: str) -> bool:
    """True wenn Hash mit alten Parametern erstellt wurde — dann neu hashen."""
    return _ph.check_needs_rehash(hashed)


def check_password_strength(password: str, user_inputs: list[str] | None = None) -> dict[str, Any]:
    """
    Passwort-Stärke mit zxcvbn prüfen.
    Score 0-4: 0=sehr schwach, 4=sehr stark.
    Mindestanforderung: Score >= 3.

    Returns:
        {"ok": bool, "score": int, "feedback": str}
    """
    result = zxcvbn_lib.zxcvbn(password, user_inputs=user_inputs or [])
    score = result["score"]
    feedback = result["feedback"]

    suggestion = ""
    if feedback["warning"]:
        suggestion = feedback["warning"]
    elif feedback["suggestions"]:
        suggestion = feedback["suggestions"][0]

    return {
        "ok": score >= 3,
        "score": score,
        "feedback": suggestion or ("Passwort ist stark." if score >= 3 else "Passwort ist zu schwach."),
    }


# =============================================================================
# JWT
# =============================================================================

def _create_token(
    subject: str,
    token_type: str,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Interner JWT-Generator."""
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,          # User-ID
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_access_token(user_id: str, roles: list[str]) -> str:
    """
    Access-Token erstellen (8 Stunden).
    Enthält Rollen für schnelle Autorisierung ohne DB-Query.
    """
    return _create_token(
        subject=user_id,
        token_type=TOKEN_TYPE_ACCESS,
        expires_delta=timedelta(minutes=settings.jwt_access_token_expire_minutes),
        extra_claims={"roles": roles},
    )


def create_refresh_token(user_id: str) -> str:
    """Refresh-Token erstellen (30 Tage)."""
    return _create_token(
        subject=user_id,
        token_type=TOKEN_TYPE_REFRESH,
        expires_delta=timedelta(days=settings.jwt_refresh_token_expire_days),
    )


def decode_token(token: str) -> dict[str, Any]:
    """
    Token dekodieren und validieren.
    Wirft JWTError bei ungültigem oder abgelaufenem Token.
    """
    return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])


def decode_access_token(token: str) -> dict[str, Any]:
    """Access-Token dekodieren — prüft auch den Token-Typ."""
    payload = decode_token(token)
    if payload.get("type") != TOKEN_TYPE_ACCESS:
        raise JWTError("Falscher Token-Typ")
    return payload


def decode_refresh_token(token: str) -> dict[str, Any]:
    """Refresh-Token dekodieren — prüft auch den Token-Typ."""
    payload = decode_token(token)
    if payload.get("type") != TOKEN_TYPE_REFRESH:
        raise JWTError("Falscher Token-Typ")
    return payload


# Cookie-Namen (konsistent verwenden)
COOKIE_ACCESS_TOKEN = "access_token"
COOKIE_REFRESH_TOKEN = "refresh_token"

# Cookie-Einstellungen (HttpOnly, Secure, SameSite=Lax)
COOKIE_SETTINGS = {
    "httponly": True,
    "secure": True,       # Nur über HTTPS
    "samesite": "lax",    # CSRF-Schutz
}
