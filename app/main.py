"""
FastAPI Application — Haupteinstiegspunkt.
Routen werden als separate Router eingebunden (auth, events, etc.)
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.database import engine
from app.routers import auth


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup und Shutdown Hooks."""
    # Startup
    yield
    # Shutdown
    await engine.dispose()


app = FastAPI(
    title="Kirchliches Planungs- und Reservationssystem",
    version="0.1.0",
    docs_url="/api/docs" if settings.is_development else None,   # Swagger nur in Dev
    redoc_url="/api/redoc" if settings.is_development else None,
    openapi_url="/api/openapi.json" if settings.is_development else None,
    lifespan=lifespan,
)

# Statische Dateien
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Templates
templates = Jinja2Templates(directory="app/templates")

# Routers einbinden
app.include_router(auth.router, prefix="/api/v1")

# Weitere Routers (werden in späteren Sessions hinzugefügt):
# app.include_router(events.router, prefix="/api/v1")
# app.include_router(calendar.router, prefix="/api/v1")
# app.include_router(locations.router, prefix="/api/v1")
# app.include_router(persons.router, prefix="/api/v1")
# app.include_router(users.router, prefix="/api/v1")
# app.include_router(duty.router, prefix="/api/v1")
# app.include_router(blackouts.router, prefix="/api/v1")
# app.include_router(admin.router, prefix="/api/v1")


# =============================================================================
# HEALTH CHECK
# =============================================================================

@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    """
    Health-Check für Docker und Monitoring.
    Gibt 200 OK zurück wenn die App läuft.
    """
    return {"status": "ok", "version": "0.1.0"}


# =============================================================================
# GLOBALER FEHLER-HANDLER
# =============================================================================

@app.exception_handler(404)
async def not_found_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"error": "not_found", "message": "Die angeforderte Ressource wurde nicht gefunden."},
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "internal_error", "message": "Interner Serverfehler. Bitte versuche es später erneut."},
    )


# =============================================================================
# STARTSEITE (SSR)
# =============================================================================

@app.get("/", include_in_schema=False)
async def index(request: Request):
    """Startseite — leitet zum Login weiter wenn nicht eingeloggt."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/login")


@app.get("/login", include_in_schema=False)
async def login_page(request: Request):
    """Login-Seite."""
    return templates.TemplateResponse(
        "auth/login.html",
        {"request": request, "title": "Anmelden"},
    )
