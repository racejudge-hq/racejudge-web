from __future__ import annotations

import os
from functools import lru_cache


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
