# routes.py
# Read-only JSON API backing the dashboard UI (static/). Admin-only:
# scan_audit_log now always includes the raw prompt (this is an enterprise
# audit/compliance product, not a generic one - see backend/audit/README.md),
# so the whole dashboard - not just that one field - requires the admin
# role. There is currently no reduced-visibility view for the viewer role;
# viewer remains meaningful for backend/auth/'s own device-management
# surface, just not for this one.

from typing import Optional

from fastapi import APIRouter, Depends, Query

from auth.dependencies import require_role
from auth import service as auth_service
from . import queries

router = APIRouter()

_require_admin = require_role("admin")


@router.get("/api/stats")
def stats(
    days: int = Query(default=7, ge=1, le=90),
    _admin: auth_service.User = Depends(_require_admin),
):
    return queries.get_stats(days=days)


@router.get("/api/events")
def events(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    decision: Optional[str] = Query(default=None),
    platform: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    _admin: auth_service.User = Depends(_require_admin),
):
    rows, total = queries.get_events(
        limit=limit, offset=offset, decision=decision, platform=platform, search=search,
    )
    return {"events": rows, "total": total, "limit": limit, "offset": offset}
