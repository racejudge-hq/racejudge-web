from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


def _load_local_env() -> None:
    """Read the repo's .env when running locally, before Settings is built.

    Every field below is resolved at class-definition time, so this has to run
    at import. Without it `uvicorn apps.api.main:app` starts fine and then 503s
    every database route -- the deployed API gets its environment from Fly, but
    a local shell only has what .env holds. `override=False` keeps a real
    exported variable ahead of the file, and python-dotenv is a dev-only
    dependency, so a deployment that lacks it simply skips this.

    Never under pytest. The API tests have no conftest and no fixture database:
    an unset DATABASE_URL is what keeps them off a real server, and reading .env
    here would silently point the whole suite at production Neon and at the live
    Stripe secret. PYTEST_VERSION is set before collection imports this module.
    """
    if "PYTEST_VERSION" in os.environ:
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=False)


_load_local_env()


class Settings:
    environment: str = os.getenv("ENVIRONMENT", "development")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    database_url: str = os.getenv("DATABASE_URL", "")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    allowed_origins: list[str] = os.getenv(
        "ALLOWED_ORIGINS", "http://localhost:3000"
    ).split(",")

    # Stripe — all optional; Stripe features are disabled when unset
    stripe_secret_key: str = os.getenv("STRIPE_SECRET_KEY", "")
    stripe_webhook_secret: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    stripe_pro_price_id: str = os.getenv("STRIPE_PRO_PRICE_ID", "")
    stripe_team_price_id: str = os.getenv("STRIPE_TEAM_PRICE_ID", "")

    @property
    def stripe_enabled(self) -> bool:
        return bool(self.stripe_secret_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
