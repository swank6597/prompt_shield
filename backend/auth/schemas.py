# schemas.py
# Pydantic request/response models for the auth API surface.

from typing import List, Optional

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    accessToken: str
    tokenType: str = "bearer"
    expiresInMinutes: int


class UserOut(BaseModel):
    id: int
    username: str
    role: str


class DeviceEnrollRequest(BaseModel):
    label: str


class DeviceEnrollResponse(BaseModel):
    id: int
    label: str
    apiKey: str  # returned exactly once, at enrollment - never retrievable again


class DeviceOut(BaseModel):
    id: int
    label: str
    ownerUserId: Optional[int] = None
    createdAt: str
    lastUsedAt: Optional[str] = None
    revokedAt: Optional[str] = None


class AuditLogEntryOut(BaseModel):
    id: int
    timestamp: str
    actorUserId: Optional[int] = None
    actorLabel: Optional[str] = None
    action: str
    target: Optional[str] = None
    success: bool
    detail: Optional[str] = None


class AuditLogPage(BaseModel):
    entries: List[AuditLogEntryOut]
    total: int
    limit: int
    offset: int
