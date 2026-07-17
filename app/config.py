from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str
    APP_ENV: str = "production"
    # MaxMind GeoIP2 Precision Web Service credentials
    # Get them from: https://www.maxmind.com/en/accounts/current/license-key
    MAXMIND_ACCOUNT_ID: str = ""
    MAXMIND_LICENSE_KEY: str = ""
    GEO_FAIL_OPEN: bool = False
    BACKEND_PROXY_SECRET: str = ""
    ORDER_TOKEN_SECRET: str = ""
    GOOGLE_SHEETS_WEBHOOK_URL: str = ""
    GOOGLE_SHEETS_WEBHOOK_SECRET: str = ""
    CONTACT_WEBHOOK_URL: str = ""
    SHEET_SYNC_POLL_SECONDS: float = 5.0
    FB_ACCESS_TOKEN: str = ""
    FB_PIXEL_ID: str = ""
    TIKTOK_ACCESS_TOKEN: str = ""
    TIKTOK_PIXEL_ID: str = ""
    SNAP_ACCESS_TOKEN: str = ""
    SNAP_PIXEL_ID: str = ""
    # Comma-separated origins, e.g. "https://lamabeauty.shop,http://localhost:3000"
    ALLOWED_ORIGINS: str = "https://lamabeauty.shop,https://www.lamabeauty.shop,http://localhost:3000,http://localhost:3001,http://localhost:3002"
    TEST_PHONE: str = ""
    ENABLE_DOCS: bool = False

    # Admin dashboard — password login with signed 12-hour session tokens.
    ADMIN_ACCESS_KEY: str = ""
    ADMIN_USERNAME: str = ""
    ADMIN_PASSWORD: str = ""
    ADMIN_JWT_SECRET: str = ""
    ENABLE_LEGACY_ADMIN_ACCESS_KEY: bool = False

    def get_allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    def get_test_phone_locals(self) -> set[str]:
        """Numbers that bypass MaxMind / Cloudflare geo blocking (local 05XXXXXXXX)."""
        from app.phone_utils import build_test_phone_locals

        return build_test_phone_locals(self.TEST_PHONE)

    def validate_runtime_security(self) -> None:
        if self.APP_ENV.lower() != "production":
            return
        required = {
            "BACKEND_PROXY_SECRET": self.BACKEND_PROXY_SECRET,
            "ORDER_TOKEN_SECRET": self.ORDER_TOKEN_SECRET,
            "ADMIN_USERNAME": self.ADMIN_USERNAME,
            "ADMIN_PASSWORD": self.ADMIN_PASSWORD,
            "ADMIN_JWT_SECRET": self.ADMIN_JWT_SECRET,
            "MAXMIND_ACCOUNT_ID": self.MAXMIND_ACCOUNT_ID,
            "MAXMIND_LICENSE_KEY": self.MAXMIND_LICENSE_KEY,
            "GOOGLE_SHEETS_WEBHOOK_URL": self.GOOGLE_SHEETS_WEBHOOK_URL,
            "GOOGLE_SHEETS_WEBHOOK_SECRET": self.GOOGLE_SHEETS_WEBHOOK_SECRET,
        }
        missing = [name for name, value in required.items() if not str(value).strip()]
        if missing:
            raise RuntimeError(f"Missing required production settings: {', '.join(missing)}")
        placeholders = ("replace-with", "your_maxmind", "your_script_id")
        invalid = [
            name
            for name, value in required.items()
            if any(marker in str(value).lower() for marker in placeholders)
        ]
        if invalid:
            raise RuntimeError(f"Replace placeholder production settings: {', '.join(invalid)}")
        for name, value in {
            "BACKEND_PROXY_SECRET": self.BACKEND_PROXY_SECRET,
            "ORDER_TOKEN_SECRET": self.ORDER_TOKEN_SECRET,
            "ADMIN_JWT_SECRET": self.ADMIN_JWT_SECRET,
            "GOOGLE_SHEETS_WEBHOOK_SECRET": self.GOOGLE_SHEETS_WEBHOOK_SECRET,
        }.items():
            if len(value.strip()) < 32:
                raise RuntimeError(f"{name} must contain at least 32 characters")
        if len(self.ADMIN_PASSWORD) < 16:
            raise RuntimeError("ADMIN_PASSWORD must contain at least 16 characters")
        if self.GEO_FAIL_OPEN:
            raise RuntimeError("GEO_FAIL_OPEN must be false in production")
        if self.TEST_PHONE.strip():
            raise RuntimeError("TEST_PHONE must be empty in production")
        if self.ENABLE_LEGACY_ADMIN_ACCESS_KEY:
            raise RuntimeError("Legacy admin access keys must be disabled in production")


settings = Settings()

# SQLAlchemy 2.0 dropped support for "postgres://" scheme
if settings.DATABASE_URL.startswith("postgres://"):
    settings.DATABASE_URL = settings.DATABASE_URL.replace("postgres://", "postgresql://", 1)
