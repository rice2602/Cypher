"""
auth.py — Password hashing (bcrypt) + JWT (PyJWT).
"""

import bcrypt
import jwt
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
# JWT (HS256 via PyJWT)
# ---------------------------------------------------------------------------

def create_jwt(
    payload: dict,
    secret: str = None,
    expires_in: int = 86400   # 24 h default
) -> str:
    """Return a signed HS256 JWT."""
    import time
    if secret is None:
        secret = settings.JWT_SECRET
    payload_copy = payload.copy()
    if "exp" not in payload_copy:
        payload_copy["exp"] = int(time.time()) + expires_in
    return jwt.encode(payload_copy, secret, algorithm="HS256")


def verify_jwt(token: str, secret: str = None) -> dict | None:
    """Verify a HS256 JWT. Returns payload dict or None if invalid/expired."""
    if secret is None:
        secret = settings.JWT_SECRET
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.exceptions.PyJWTError:
        return None
