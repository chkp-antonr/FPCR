import os

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env and .env.secrets for os.getenv() to work
load_dotenv()  # Load .env first
load_dotenv(".env.secrets", override=True)  # Then .env.secrets (overrides)


class WebUISettings(BaseSettings):
    """WebUI configuration settings."""

    model_config = SettingsConfigDict(
        env_prefix="WEBUI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8000
    secret_key: str = ""
    session_age_hours: int = 8
    cors_origins: str = "http://localhost:5173,http://localhost:8000,http://localhost:8080"
    # Single SQLite database for both cache (async) and sessions (sync)
    database_url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///_tmp/cache.db")

    # RITM approval lock timeout in minutes
    approval_lock_minutes: int = 30

    @property
    def sqlite_db_path(self) -> str:
        """Extract local file path from the SQLAlchemy database_url (cache DB)."""
        if "///" in self.database_url:
            return self.database_url.split("///")[-1]
        return "cache.db"

    # Check Point connection (shared from main env)
    api_mgmt: str = os.getenv("API_MGMT", "")

    # RADIUS (future - not used in MVP)
    radius_server: str | None = None
    radius_secret: str | None = None
    radius_timeout: int = 5

    # FPCR Create & Verify flow settings
    initials_csv_path: str = "_tmp/FWTeam_admins.csv"
    evidence_template_dir: str = "src/fa/templates"
    pdf_render_timeout: int = 30

    # Object creation settings
    object_create_missing: bool = True
    object_prefer_convention: bool = True

    # Rule creation settings
    rule_disable_after_create: bool = True
    rule_verify_after_create: bool = True

    @property
    def cors_origins_list(self) -> list[str]:
        """Return CORS origins as a list."""
        return [s.strip() for s in self.cors_origins.split(",") if s.strip()]


def _generate_secret_key() -> str:
    """Generate a Fernet-compatible secret key if not set."""
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode()


# Global settings instance - generate secret key if missing
_secret_key = os.getenv("WEBUI_SECRET_KEY")
if not _secret_key:
    _secret_key = _generate_secret_key()
    print(f"Generated WEBUI_SECRET_KEY: {_secret_key}")

settings = WebUISettings(
    secret_key=_secret_key,
)
