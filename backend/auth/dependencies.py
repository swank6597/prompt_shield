# dependencies.py
# FastAPI Depends()/Security() guards used by routes.py (auth's own routes)
# and by backend/routes.py's /api/scan handler.
#
# Uses fastapi.security's APIKeyHeader/HTTPBearer (not a raw Header()) so
# Swagger UI (/docs, /auth/docs, /devices/docs) shows a proper "Authorize"
# button per scheme - paste just the API key or just the token, no need to
# type "Bearer <token>" by hand into a per-request field.

from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from . import service
from .security import decode_access_token

_api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)
_bearer_scheme = HTTPBearer(auto_error=False)


def require_api_key(x_api_key: Optional[str] = Security(_api_key_scheme)) -> service.Device:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    device = service.resolve_device(x_api_key)
    if device is None:
        raise HTTPException(status_code=401, detail="Invalid or revoked API key")
    return device


def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(_bearer_scheme),
) -> Optional[service.User]:
    """Like get_current_user, but returns None instead of raising when no
    (or an invalid) bearer token is present - used by /devices/enroll,
    which works either as an anonymous device or bound to a logged-in user."""
    if credentials is None:
        return None
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.PyJWTError:
        return None
    return service.get_user_by_id(int(payload["sub"]))


def get_current_user(
    user: Optional[service.User] = Depends(get_current_user_optional),
) -> service.User:
    if user is None:
        raise HTTPException(status_code=401, detail="Missing, invalid, or expired bearer token")
    return user


def require_role(role: str):
    def _check(user: service.User = Depends(get_current_user)) -> service.User:
        if user.role != role:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return _check
