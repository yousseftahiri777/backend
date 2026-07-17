"""Admin password authentication with signed short-lived bearer sessions."""

import base64
import hmac
import secrets
import time
from hashlib import sha256

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

_bearer = HTTPBearer(auto_error=False)
TOKEN_TTL_SECONDS = 60 * 60 * 12


def _jwt_secret() -> bytes:
    return settings.ADMIN_JWT_SECRET.strip().encode()


def verify_access_key(key: str) -> bool:
    cfg = settings.ADMIN_ACCESS_KEY.strip()
    if not cfg or not key:
        return False
    return secrets.compare_digest(key, cfg)


def create_admin_token(username: str) -> tuple[str, int]:
    if not _jwt_secret():
        raise RuntimeError("ADMIN_JWT_SECRET is not configured")
    exp = int(time.time()) + TOKEN_TTL_SECONDS
    payload = f"{username}:{exp}"
    sig = hmac.new(_jwt_secret(), payload.encode(), sha256).hexdigest()
    token = base64.urlsafe_b64encode(f"{payload}:{sig}".encode()).decode()
    return token, exp


def verify_admin_token(token: str) -> str | None:
    if not _jwt_secret():
        return None
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        payload, sig = decoded.rsplit(":", 1)
        username, exp_str = payload.split(":", 1)
        exp = int(exp_str)
        if exp < time.time():
            return None
        expected = hmac.new(_jwt_secret(), payload.encode(), sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        return username
    except Exception:
        return None


def verify_admin_credentials(username: str, password: str) -> bool:
    cfg_user = settings.ADMIN_USERNAME.strip()
    cfg_pass = settings.ADMIN_PASSWORD.strip()
    if not cfg_user or not cfg_pass:
        return False
    return secrets.compare_digest(username, cfg_user) and secrets.compare_digest(password, cfg_pass)


def require_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    x_admin_access_key: str | None = Header(None, alias="X-Admin-Access-Key"),
) -> str:
    if (
        settings.ENABLE_LEGACY_ADMIN_ACCESS_KEY
        and x_admin_access_key
        and verify_access_key(x_admin_access_key)
    ):
        return "admin"

    if credentials and credentials.scheme.lower() == "bearer":
        username = verify_admin_token(credentials.credentials)
        if username:
            return username

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
