# routes.py
# HTTP endpoints for authentication: login/session and device identity
# management. Thin - delegates to service.py.
#
# Split into two routers (auth_router, device_router) rather than one,
# because app.py mounts each under its own path prefix ("/auth", "/devices")
# with its own CORSMiddleware instance - see app.py's comment for why a
# single global CORSMiddleware can't give these routes a different origin
# policy than the wildcard one /api/scan needs (specs/authentication/
# Requirement 8.1). Because of that mounting, paths here are relative
# ("/login", not "/auth/login") - the prefix is added by the mount.

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends

from . import service
from .dependencies import get_current_user, get_current_user_optional, require_role
from .security import issue_access_token
from .schemas import (
    LoginRequest,
    TokenResponse,
    UserOut,
    DeviceEnrollRequest,
    DeviceEnrollResponse,
    DeviceOut,
    AuditLogEntryOut,
    AuditLogPage,
)
from config import AUTH_TOKEN_EXPIRE_MINUTES

auth_router = APIRouter()
device_router = APIRouter()


@auth_router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest):
    try:
        user = service.authenticate_user(request.username, request.password)
    except service.AccountLockedError:
        user = None
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = issue_access_token(user.id, user.role)
    return TokenResponse(accessToken=token, expiresInMinutes=AUTH_TOKEN_EXPIRE_MINUTES)


@auth_router.post("/logout")
def logout(user: service.User = Depends(get_current_user)):
    # Stateless JWT - nothing to invalidate server-side in v1 (see design.md);
    # this endpoint exists so the audit log records the intentional logout.
    service.record_audit_event("logout", actor_user_id=user.id, actor_label=user.username,
                                target=user.username, success=True)
    return {"status": "ok"}


@auth_router.get("/me", response_model=UserOut)
def me(user: service.User = Depends(get_current_user)):
    return UserOut(id=user.id, username=user.username, role=user.role)


@auth_router.get("/audit-log", response_model=AuditLogPage)
def audit_log(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    actor_user_id: Optional[int] = Query(default=None),
    action: Optional[str] = Query(default=None),
    _admin: service.User = Depends(require_role("admin")),
):
    entries, total = service.get_audit_log(limit=limit, offset=offset,
                                            actor_user_id=actor_user_id, action=action)
    return AuditLogPage(
        entries=[
            AuditLogEntryOut(
                id=e["id"], timestamp=e["timestamp"], actorUserId=e["actor_user_id"],
                actorLabel=e["actor_label"], action=e["action"], target=e["target"],
                success=bool(e["success"]), detail=e["detail"],
            )
            for e in entries
        ],
        total=total, limit=limit, offset=offset,
    )


@device_router.post("/enroll", response_model=DeviceEnrollResponse)
def enroll_device(request: DeviceEnrollRequest, caller: Optional[service.User] = Depends(get_current_user_optional)):
    owner_user_id = caller.id if caller else None
    device, api_key = service.create_device(request.label, owner_user_id=owner_user_id)
    return DeviceEnrollResponse(id=device.id, label=device.label, apiKey=api_key)


@device_router.get("/", response_model=list[DeviceOut])
def list_devices(_admin: service.User = Depends(require_role("admin"))):
    return [
        DeviceOut(
            id=d.id, label=d.label, ownerUserId=d.owner_user_id, createdAt=d.created_at,
            lastUsedAt=d.last_used_at, revokedAt=d.revoked_at,
        )
        for d in service.list_devices()
    ]


@device_router.post("/{device_id}/revoke")
def revoke_device(device_id: int, admin: service.User = Depends(require_role("admin"))):
    revoked = service.revoke_device(device_id, acting_admin=admin)
    if not revoked:
        raise HTTPException(status_code=404, detail="Device not found or already revoked")
    return {"status": "revoked", "deviceId": device_id}
