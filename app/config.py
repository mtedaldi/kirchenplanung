"""
Zentrale Konfiguration via Umgebungsvariablen (.env).
Alle Werte kommen aus der .env-Datei — niemals Secrets im Code.
"""
from pydantic import PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # App
    app_env: str = "production"
    app_base_url: str = "https://kirchenplanung.example.ch"
    debug: bool = False

    # Datenbank
    database_url: PostgresDsn

    # JWT
    secret_key: str
    jwt_access_token_expire_minutes: int = 480       # 8 Stunden
    jwt_refresh_token_expire_days: int = 30

    # Archivierung
    archive_retention_years: int = 2

    # Backup
    backup_local_dir: str = "/var/backups/kirchenplanung"
    backup_retention_days: int = 90

    @field_validator("secret_key")
    @classmethod
    def secret_key_must_be_long(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY muss mindestens 32 Zeichen lang sein")
        return v

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def async_database_url(self) -> str:
        """asyncpg-kompatible URL (postgresql+asyncpg://)"""
        url = str(self.database_url)
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url


# Singleton — einmal laden, überall verwenden
settings = Settings()  # type: ignore[call-arg]
