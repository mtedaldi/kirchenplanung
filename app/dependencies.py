"""
FastAPI Dependencies für Authentifizierung und Autorisierung.

Jeder geschützte Endpunkt verwendet mindestens require_authenticated_user().
Rollengeschützte Endpunkte verwenden require_role("approver", "admin") etc.
Ownership-Checks verwenden require_event_owner_or_admin() etc.

Konvention aus API-Spec V0.2.1:
  - x-required-roles → Depends(require_role(...))
  - x-ownership-check → Depends(require_*_owner_or_admin(...))
"""
import uuid
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import COOKIE_ACCESS_TOKEN, decode_access_token
from app.database import get_db
from app.models import AppUser, Event


# =============================================================================
# AUTHENTICATED USER
# =============================================================================

async def get_current_user(
    access_token: Annotated[str | None, Cookie(alias=COOKIE_ACCESS_TOKEN)] = None,
    db: AsyncSession = Depends(get_db),
) -> AppUser:
    """
    Dependency: Gibt den eingeloggten User zurück.
    Wirft 401 wenn nicht eingeloggt oder Token ungültig.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Nicht eingeloggt oder Session abgelaufen.",
    )

    if not access_token:
        raise credentials_exception

    try:
        payload = decode_access_token(access_token)
        user_id: str = payload.get("sub", "")
        if not user_id:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # User aus DB laden mit Rollen
    result = await db.execute(
        select(AppUser)
        .options(selectinload(AppUser.roles).selectinload(AppUser.roles))
        .where(AppUser.id == uuid.UUID(user_id))
        .where(AppUser.deleted_at.is_(None))
        .where(AppUser.is_active.is_(True))
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    return user


# Shorthand-Typ für Dependency Injection
CurrentUser = Annotated[AppUser, Depends(get_current_user)]


# =============================================================================
# RBAC — ROLLENPRÜFUNG
# =============================================================================

def require_role(*roles: str):
    """
    Factory-Dependency: Prüft ob User mindestens eine der angegebenen Rollen hat.

    Verwendung:
        @router.post("/events/{id}/approve")
        async def approve(
            user: CurrentUser,
            _: Annotated[None, Depends(require_role("approver", "admin"))],
        ):
            ...
    """
    async def _check(user: CurrentUser) -> None:
        user_roles = {ur.role.name for ur in user.roles if ur.role}
        if not user_roles.intersection(set(roles)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Erfordert eine der Rollen: {', '.join(roles)}",
            )
    return _check


# Vordefinierte Rollen-Dependencies
RequireRequester = Depends(require_role("requester", "approver", "admin"))
RequireApprover = Depends(require_role("approver", "admin"))
RequireAdmin = Depends(require_role("admin"))


# =============================================================================
# OWNERSHIP — SELBST ODER ADMIN
# =============================================================================

def require_event_owner_or_admin(event_id_param: str = "event_id"):
    """
    Prüft ob der aktuelle User den Anlass erstellt hat, oder Admin ist.
    Wirft 403 wenn weder noch, 404 wenn Anlass nicht gefunden.

    Verwendung:
        @router.patch("/events/{event_id}")
        async def update_event(
            event_id: uuid.UUID,
            _: Annotated[None, Depends(require_event_owner_or_admin())],
            user: CurrentUser,
            db: AsyncSession = Depends(get_db),
        ):
            ...
    """
    async def _check(
        event_id: uuid.UUID,
        user: CurrentUser,
        db: AsyncSession = Depends(get_db),
    ) -> None:
        result = await db.execute(
            select(Event)
            .where(Event.id == event_id)
            .where(Event.deleted_at.is_(None))
        )
        event = result.scalar_one_or_none()

        if event is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anlass nicht gefunden.")

        user_roles = {ur.role.name for ur in user.roles if ur.role}
        is_admin = "admin" in user_roles
        is_owner = event.created_by == user.id

        if not (is_owner or is_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Nur der Ersteller oder ein Admin darf diesen Anlass bearbeiten.",
            )

    return _check


def require_not_self_approval(event_id_param: str = "event_id"):
    """
    Prüft Self-Approval-Verbot: Der User darf seinen eigenen Anlass nicht freigeben.
    Zusätzlich zur DB-Constraint — Defense in Depth.
    """
    async def _check(
        event_id: uuid.UUID,
        user: CurrentUser,
        db: AsyncSession = Depends(get_db),
    ) -> None:
        result = await db.execute(
            select(Event.created_by)
            .where(Event.id == event_id)
            .where(Event.deleted_at.is_(None))
        )
        created_by = result.scalar_one_or_none()

        if created_by is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anlass nicht gefunden.")

        if created_by == user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Self-Approval ist verboten. Du kannst deinen eigenen Anlass nicht freigeben.",
            )

    return _check
