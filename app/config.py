from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "postgres://lamabeauty:lamabeauty@lamabeauty_database:5432/lamabeauty?sslmode=disable"
    # MaxMind GeoIP2 Precision Web Service credentials
    # Get them from: https://www.maxmind.com/en/accounts/current/license-key
    MAXMIND_ACCOUNT_ID: str = ""
    MAXMIND_LICENSE_KEY: str = ""
    GOOGLE_SHEETS_WEBHOOK_URL: str = ""
    FB_ACCESS_TOKEN: str = ""
    FB_PIXEL_ID: str = ""
    TIKTOK_ACCESS_TOKEN: str = ""
    TIKTOK_PIXEL_ID: str = ""
    # From Events Manager → Test events (shows Server events in the test panel)
    TIKTOK_TEST_EVENT_CODE: str = ""
    SNAP_ACCESS_TOKEN: str = ""
    SNAP_PIXEL_ID: str = ""
    # Comma-separated origins, e.g. "https://lamabeauty.shop,http://localhost:3000"
    ALLOWED_ORIGINS: str = "https://lamabeauty.shop,https://www.lamabeauty.shop,http://localhost:3000,http://localhost:3001,http://localhost:3002"
    TEST_PHONE: str = "0550000000"

    # Admin dashboard — secret URL key (recommended) or username/password fallback
    ADMIN_ACCESS_KEY: str = ""
    ADMIN_USERNAME: str = ""
    ADMIN_PASSWORD: str = ""
    ADMIN_JWT_SECRET: str = ""

    def get_allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    def get_test_phone_locals(self) -> set[str]:
        """Numbers that bypass MaxMind / Cloudflare geo blocking (local 05XXXXXXXX)."""
        primary = (self.TEST_PHONE or "0550000000").strip() or "0550000000"
        from app.phone_utils import build_test_phone_locals

        return build_test_phone_locals(primary, "0513194328")


settings = Settings()

# SQLAlchemy 2.0 dropped support for "postgres://" scheme
if settings.DATABASE_URL.startswith("postgres://"):
    settings.DATABASE_URL = settings.DATABASE_URL.replace("postgres://", "postgresql://", 1)
