"""Runtime settings, read from environment variables and the git-ignored `.env` file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
DEFAULT_DEV_DATABASE_URL = (
    "postgresql+psycopg://garminizer:garminizer-dev@127.0.0.1:55432/garminizer"
)


class ConfigError(RuntimeError):
    """Raised when the configuration is unsafe or incomplete."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = DEFAULT_DEV_DATABASE_URL

    app_host: str = "127.0.0.1"  # who may reach the dashboard (safety check)
    app_port: int = 8420
    listen_host: str | None = None  # bind address; Docker sets 0.0.0.0 behind a 127.0.0.1 port map
    web_dist: Path | None = None  # built SPA (defaults to web/dist in a source checkout)
    app_password: SecretStr | None = None
    app_secret_key: SecretStr | None = None

    garmin_email: str | None = None
    garmin_password: SecretStr | None = None

    data_dir: Path = Path("data")
    garmin_token_dir: Path | None = None
    backup_dir: Path | None = None
    backup_keep: int = 14

    sync_interval_hours: float = 2.0
    sync_request_delay_s: float = 1.0
    tz: str = "UTC"

    map_style_url: str = "https://tiles.openfreemap.org/styles/positron"
    map_style_url_dark: str = "https://tiles.openfreemap.org/styles/dark"

    @field_validator("app_password", "app_secret_key", "garmin_password", mode="before")
    @classmethod
    def _empty_secret_is_none(cls, value: object) -> object:
        return None if value in ("", None) else value

    @field_validator("garmin_email", mode="before")
    @classmethod
    def _empty_str_is_none(cls, value: object) -> object:
        return None if value == "" else value

    @property
    def token_dir(self) -> Path:
        return self.garmin_token_dir or self.data_dir / "tokens"

    @property
    def backups_dir(self) -> Path:
        return self.backup_dir or self.data_dir / "backups"

    @property
    def bind_host(self) -> str:
        return self.listen_host or self.app_host

    @property
    def is_loopback(self) -> bool:
        return self.app_host in LOOPBACK_HOSTS

    def check_web_safety(self) -> None:
        """Refuse to serve personal health data beyond this computer without a password."""
        if not self.is_loopback and self.app_password is None:
            raise ConfigError(
                f"APP_HOST={self.app_host} exposes the dashboard to your network, "
                "so APP_PASSWORD must be set in .env (or use APP_HOST=127.0.0.1)."
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
