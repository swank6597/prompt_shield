# security.py
# Password/API-key hashing and JWT access-token issuance/verification.
# No other module in backend/auth/ should touch bcrypt or jwt directly -
# this is the only place those primitives are used.

import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from config import AUTH_SECRET_KEY, AUTH_TOKEN_EXPIRE_MINUTES, AUTH_BCRYPT_ROUNDS

if not AUTH_SECRET_KEY:
    raise RuntimeError(
        "PROMPTSHIELD_AUTH_SECRET_KEY is not set. Generate one with "
        "`python -c \"import secrets; print(secrets.token_urlsafe(32))\"` "
        "and add it to backend/.env - refusing to sign tokens with no key."
    )

_JWT_ALGORITHM = "HS256"


def hash_secret(plaintext: str) -> str:
    """Hashes a password or API key with bcrypt. Used for both - a device
    API key is just another bearer secret."""
    salt = bcrypt.gensalt(rounds=AUTH_BCRYPT_ROUNDS)
    return bcrypt.hashpw(plaintext.encode("utf-8"), salt).decode("utf-8")


def verify_secret(plaintext: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plaintext.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        # Malformed hash (e.g. corrupted row) - never a match.
        return False


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)


def issue_access_token(user_id: int, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=AUTH_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, AUTH_SECRET_KEY, algorithm=_JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Raises jwt.PyJWTError (or a subclass) if the token is missing,
    malformed, tampered, or expired - callers should catch that broadly."""
    return jwt.decode(token, AUTH_SECRET_KEY, algorithms=[_JWT_ALGORITHM])
