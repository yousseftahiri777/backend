from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import List


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
    ALLOWED_ORIGINS: List[str] = ["https://lamabeauty.shop", "http://localhost:3000"]
    TEST_PHONE: str = "0550000000"

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v


settings = Settings()
