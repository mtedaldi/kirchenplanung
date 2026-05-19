"""
Datenbankverbindung via SQLAlchemy async + asyncpg.
Alle DB-Operationen laufen async — kein blocking I/O.
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# Engine: asyncpg-Treiber, Pool-Grösse für MVP ausreichend
engine = create_async_engine(
    settings.async_database_url,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,   # Stale connections erkennen
    echo=settings.is_development,  # SQL-Logging nur in Dev
)

# Session-Factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Objekte nach commit noch lesbar
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Basisklasse für alle SQLAlchemy-Modelle."""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI Dependency: liefert eine DB-Session pro Request.
    Session wird nach dem Request automatisch geschlossen.

    Verwendung in Routen:
        async def my_route(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    Erstellt alle Tabellen (nur für Tests / Ersteinrichtung).
    In Produktion: Alembic-Migrationen verwenden.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
