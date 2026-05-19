"""
Auth-Router: Login, Logout, Token-Refresh, Profil, Passwort ändern.
JWT wird als HttpOnly-Cookie gesetzt — nie im Response-Body.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from jose import JWTError
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import (
    COOKIE_ACCESS_TOKEN,
    COOKIE_REFRESH_TOKEN,
    COOKIE_SETTINGS,
    check_password_strength,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.database import get_db
from app.dependencies import CurrentUser
from app.models import AppUser, Person

router = APIRouter(prefix="/auth", tags=["auth"])


# =============================================================================
# SCHEMAS
# =============================================================================

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_strength(cls, v: str) -> str:
        if len(v) < 10:
            raise ValueError("Passwort muss mindestens 10 Zeichen lang sein.")
        result = check_password_strength(v)
        if not result["ok"]:
            raise ValueError(f"Passwort zu schwach: {result['feedback']}")
        return v


class UserProfileResponse(BaseModel):
    id: uuid.UUID
    email: str
    roles: list[str]
    person_name: str
    last_login_at: datetime | None

    model_config = {"from_attributes": True}


# =============================================================================
# HELPER
# =============================================================================

def _set_auth_cookies(response: Response, user_id: str, roles: list[str]) -> None:
    """Setzt Access- und Refresh-Token als HttpOnly-Cookies."""
    access_token = create_access_token(user_id, roles)
    refresh_token = create_refresh_token(user_id)

    response.set_cookie(
        key=COOKIE_ACCESS_TOKEN,
        value=access_token,
        max_age=8 * 3600,  # 8 Stunden
        **COOKIE_SETTINGS,
    )
    response.set_cookie(
        key=COOKIE_REFRESH_TOKEN,
        value=refresh_token,
        max_age=30 * 24 * 3600,  # 30 Tage
        **COOKIE_SETTINGS,
    )


def _clear_auth_cookies(response: Response) -> None:
    """Löscht Auth-Cookies (Logout)."""
    response.delete_cookie(COOKIE_ACCESS_TOKEN)
    response.delete_cookie(COOKIE_REFRESH_TOKEN)


# =============================================================================
# ENDPUNKTE
# =============================================================================

@router.post("/login", summary="Einloggen")
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Login mit E-Mail und Passwort.
    Gibt JWT als HttpOnly-Cookie zurück.
    """
    # User suchen
    result = await db.execute(
        select(AppUser)
        .options(
            selectinload(AppUser.roles).selectinload(AppUser.roles),
            selectinload(AppUser.person),
        )
        .where(AppUser.email == body.email)
        .where(AppUser.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    # Timing-sicherer Vergleich: auch bei nicht existierendem User hashen
    if user is None or not user.password_hash:
        # Dummy-Hash verhindert Timing-Angriffe
        verify_password("dummy", "$argon2id$v=19$m=65536,t=2,p=2$dummy$dummy")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-Mail oder Passwort falsch.",
        )

    if not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-Mail oder Passwort falsch.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Konto ist deaktiviert. Bitte Admin kontaktieren.",
        )

    # Passwort-Hash aktualisieren falls veraltet (Argon2-Parameter-Update)
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)

    # last_login_at aktualisieren
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    # Rollen laden
    roles = [ur.role.name for ur in user.roles if ur.role]

    # Cookies setzen
    _set_auth_cookies(response, str(user.id), roles)

    return {
        "user_id": str(user.id),
        "email": user.email,
        "roles": roles,
    }


@router.post("/logout", summary="Ausloggen", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    _: CurrentUser,  # Stellt sicher dass eingeloggt
) -> None:
    """Löscht JWT-Cookies. Session ist danach beendet."""
    _clear_auth_cookies(response)


@router.post("/refresh", summary="Access-Token erneuern")
async def refresh_token(
    response: Response,
    refresh_token: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Erneuert Access-Token via Refresh-Token-Cookie."""
    from fastapi import Cookie as FastAPICookie

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Ungültiger oder abgelaufener Refresh-Token.",
    )

    if not refresh_token:
        raise credentials_exception

    try:
        payload = decode_refresh_token(refresh_token)
        user_id = payload.get("sub", "")
    except JWTError:
        raise credentials_exception

    result = await db.execute(
        select(AppUser)
        .options(selectinload(AppUser.roles).selectinload(AppUser.roles))
        .where(AppUser.id == uuid.UUID(user_id))
        .where(AppUser.is_active.is_(True))
        .where(AppUser.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    roles = [ur.role.name for ur in user.roles if ur.role]
    _set_auth_cookies(response, str(user.id), roles)

    return {"message": "Token erneuert."}


@router.get("/me", summary="Aktuell eingeloggter Benutzer")
async def get_me(user: CurrentUser) -> UserProfileResponse:
    """Gibt Profil des eingeloggten Benutzers zurück."""
    return UserProfileResponse(
        id=user.id,
        email=user.email,
        roles=[ur.role.name for ur in user.roles if ur.role],
        person_name=user.person.name if user.person else "",
        last_login_at=user.last_login_at,
    )


@router.put(
    "/me/password",
    summary="Eigenes Passwort ändern",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def change_password(
    body: ChangePasswordRequest,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Passwort ändern. Erfordert aktuelles Passwort zur Bestätigung."""
    if not user.password_hash or not verify_password(body.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Aktuelles Passwort ist falsch.",
        )

    user.password_hash = hash_password(body.new_password)
    await db.commit()
