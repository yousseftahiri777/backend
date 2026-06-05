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
    SNAP_ACCESS_TOKEN: str = ""
    SNAP_PIXEL_ID: str = ""
    # Comma-separated origins, e.g. "https://lamabeauty.shop,http://localhost:3000"
    ALLOWED_ORIGINS: str = "https://lamabeauty.shop,http://localhost:3000"
    TEST_PHONE: str = "0550000000"

    def get_allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


settings = Settings()
