"""
auth.py — Password hashing + JWT (zero external dependency JWT, bcrypt for passwords).
"""

import hmac
import hashlib
import base64
import json
import time
import bcrypt
from app.config import settings


# ---------------------------------------------------------------------------
# Password hashing (bcrypt)
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    """Hash a plain-text password with bcrypt."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if plain matches the stored bcrypt hash."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# JWT (HS256, stdlib only — no PyJWT dependency)
# ---------------------------------------------------------------------------

def _b64url_encode(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("utf-8")


def _b64url_decode(s: str) -> bytes:
    padding = "=" * (4 - (len(s) % 4))
    return base64.urlsafe_b64decode(s + padding)


def create_jwt(
    payload: dict,
    secret: str = None,
    expires_in: int = 86400   # 24 h default
) -> str:
    """Return a signed HS256 JWT."""
    if secret is None:
        secret = settings.JWT_SECRET
    header = {"alg": "HS256", "typ": "JWT"}
    payload_copy = payload.copy()
    if "exp" not in payload_copy:
        payload_copy["exp"] = int(time.time()) + expires_in

    h = _b64url_encode(json.dumps(header).encode())
    p = _b64url_encode(json.dumps(payload_copy).encode())
    sig_data = f"{h}.{p}".encode()
    sig = hmac.new(secret.encode(), sig_data, hashlib.sha256).digest()
    return f"{h}.{p}.{_b64url_encode(sig)}"


def verify_jwt(token: str, secret: str = None) -> dict | None:
    """Verify a HS256 JWT. Returns payload dict or None if invalid/expired."""
    if secret is None:
        secret = settings.JWT_SECRET
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        h, p, sig = parts
        sig_data = f"{h}.{p}".encode()
        expected = _b64url_encode(
            hmac.new(secret.encode(), sig_data, hashlib.sha256).digest()
        )
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_b64url_decode(p).decode())
        if "exp" in payload and payload["exp"] < time.time():
            return None
        return payload
    except Exception:
        return None
