# Design Document: Authentication

## Overview

Two independent identity mechanisms share one new `backend/auth/` module and one
SQLite database:

- **Device/API-key identity** protects and attributes `/api/scan` calls (machine-to-
  machine, no login UI).
- **User accounts + JWT sessions** protect the future dashboard and the
  device-management endpoints (person-to-server, real login).

Both write to the same `auth_audit_log` table so admin actions are monitored exactly
like everyone else's, per Requirement 7.

The design deliberately avoids assuming a deployment model: password hashing, token
signing, and rate-limiting are all in-process and work identically whether the backend
stays on localhost or moves behind a real network boundary later (only CORS/TLS
termination changes at deploy time, not the auth logic itself).

## Architecture

```
Browser Extension                         Backend (FastAPI)
┌──────────────┐  X-API-Key header  ┌─────────────────────────────────────┐
│ enroll once  │───────────────────▶│ POST /devices/enroll                │
│ (background) │                    │   -> auth/service.py: create_device │
└──────────────┘                    │                                     │
┌──────────────┐  X-API-Key header  │ POST /api/scan  (existing route)    │
│ every scan   │───────────────────▶│   -> Depends(require_api_key)       │
└──────────────┘                    │      resolves device_id/owner       │
                                     │                                     │
Dashboard (future)   Authorization: Bearer <JWT>                          │
┌──────────────┐───────────────────▶│ POST /auth/login                    │
│ login form   │                    │   -> auth/service.py: authenticate  │
└──────────────┘                    │ GET  /auth/me                       │
                                     │ POST /devices/{id}/revoke  (admin)  │
                                     │ GET  /auth/audit-log       (admin)  │
                                     │   -> Depends(require_role("admin")) │
                                     └─────────────────────────────────────┘
                                                    │
                                                    ▼
                                     auth.db (SQLite): users, devices,
                                     auth_audit_log
```

### Module Layout (`backend/auth/`)

| File | Responsibility |
|---|---|
| `db.py` | SQLite connection helper + schema creation (idempotent `CREATE TABLE IF NOT EXISTS`) |
| `security.py` | Password hashing/verification (bcrypt), JWT issuance/decoding |
| `schemas.py` | Pydantic request/response models |
| `service.py` | Business logic: `authenticate_user`, `create_device`, `revoke_device`, `record_audit_event`, lockout tracking |
| `dependencies.py` | FastAPI `Depends` guards: `require_api_key`, `get_current_user`, `require_role` |
| `routes.py` | Endpoint definitions, thin — delegates to `service.py` |

This mirrors the existing `backend/policy/` split (engine logic vs. rules data) and
`backend/ai/`'s per-responsibility file layout.

## Data Models

SQLite file: `backend/auth/auth.db` (git-ignored, created on first run — same pattern
as the planned dashboard's `promptshield.db`, kept as a separate file so auth data and
scan-event audit data can have independent retention policies).

```sql
CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('admin', 'viewer')),
    is_active     INTEGER NOT NULL DEFAULT 1,
    auth_provider TEXT NOT NULL DEFAULT 'local',   -- unused today, reserved for SSO
    external_id   TEXT,                            -- unused today, reserved for SSO
    failed_attempts    INTEGER NOT NULL DEFAULT 0,
    locked_until       TEXT,                       -- ISO timestamp, NULL if not locked
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE devices (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    label         TEXT NOT NULL,
    key_hash      TEXT NOT NULL UNIQUE,             -- bcrypt hash of the API key
    owner_user_id INTEGER REFERENCES users(id),      -- NULL if unbound
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    last_used_at  TEXT,
    revoked_at    TEXT                               -- NULL while active
);

CREATE TABLE auth_audit_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     TEXT NOT NULL DEFAULT (datetime('now')),
    actor_user_id INTEGER,                           -- NULL for unauthenticated attempts (e.g. bad login)
    actor_label   TEXT,                              -- username/device label at time of action, for readability if the actor is later deleted
    action        TEXT NOT NULL,                     -- e.g. 'login_success', 'login_failure', 'device_enroll', 'device_revoke', 'account_locked'
    target        TEXT,                               -- e.g. device id or affected username
    success       INTEGER NOT NULL,
    detail        TEXT                                -- short human-readable note, never a secret/password
);
```

Notes:
- `key_hash` and `password_hash` use the same bcrypt scheme (`security.py` exposes one
  `hash_secret`/`verify_secret` pair used for both) — a device API key is just another
  bearer secret.
- `auth_audit_log` has no foreign-key `ON DELETE` cascade concerns because nothing in
  this spec deletes users or devices (revocation is a flag, not a delete).

## Components and Interfaces

### 1. `security.py`

```python
def hash_secret(plaintext: str) -> str: ...          # bcrypt, cost factor from config
def verify_secret(plaintext: str, hashed: str) -> bool: ...

def issue_access_token(user_id: int, role: str) -> str: ...   # JWT, HS256, exp claim
def decode_access_token(token: str) -> dict: ...               # raises on invalid/expired

def generate_api_key() -> str: ...                    # secrets.token_urlsafe(32)
```

`issue_access_token`/`decode_access_token` use `PyJWT` with the secret from
`config.AUTH_SECRET_KEY`. Claims: `{"sub": user_id, "role": role, "exp": ...}`.

### 2. `service.py`

```python
def authenticate_user(username: str, password: str) -> User | None:
    # checks lockout window first; on failure increments failed_attempts and
    # audit-logs 'login_failure'; on success resets failed_attempts and
    # audit-logs 'login_success'

def create_device(label: str, owner_user_id: int | None) -> tuple[Device, str]:
    # returns (device_row, plaintext_api_key) — plaintext only exists in this
    # return value and the HTTP response; never persisted or logged

def resolve_device(api_key: str) -> Device | None:
    # looks up by hashing the presented key and matching key_hash;
    # returns None if not found or revoked_at is set
    # NOTE: this is an O(n) bcrypt-compare loop over active devices at v1
    # scale (see "Known limitation" below) — acceptable for the handful of
    # devices in this project's current usage, revisit if that changes.

def revoke_device(device_id: int, acting_admin_id: int) -> None: ...

def record_audit_event(action: str, actor_user_id: int | None,
                        actor_label: str | None, target: str | None,
                        success: bool, detail: str = "") -> None: ...
```

**Known limitation, called out rather than silently accepted:** bcrypt hashes can't be
looked up by index, so `resolve_device` compares the presented key against every
active device's hash. This is fine at hackathon/small-team scale; if device count
grows large, switch to a fast indexable hash (SHA-256) for the lookup key while
keeping bcrypt (or equivalent slow hash) for password storage specifically. Flagging
this now so it isn't mistaken for an oversight later — same trade-off is not made for
`password_hash`, since login volume is naturally per-human, not per-request.

### 3. `dependencies.py`

```python
def require_api_key(x_api_key: str = Header(...)) -> Device: ...
    # 401 if missing/invalid/revoked; used by /api/scan

def get_current_user(authorization: str = Header(...)) -> User: ...
    # decodes bearer JWT, 401 if missing/invalid/expired

def require_role(role: str):
    def _check(user: User = Depends(get_current_user)) -> User:
        if user.role != role: raise HTTPException(403)
        return user
    return _check
```

### 4. `routes.py` — endpoint surface

| Method & Path | Auth | Description |
|---|---|---|
| `POST /auth/login` | none | Requirement 5 |
| `POST /auth/logout` | Bearer | client-side token discard (stateless JWT; no server-side revocation list in v1) |
| `GET /auth/me` | Bearer | Requirement 5.5 |
| `GET /auth/audit-log` | Bearer, role=admin | Requirement 7.3, paginated + filterable |
| `POST /devices/enroll` | none, or Bearer to bind owner | Requirement 1 |
| `GET /devices` | Bearer, role=admin | list devices for management |
| `POST /devices/{id}/revoke` | Bearer, role=admin | Requirement 3 |

`/api/scan` in `backend/routes.py` gains `device: Device = Depends(require_api_key)`
and passes `device.id` / `device.owner_user_id` through to wherever the scan-event
audit row is written (that write itself belongs to the dashboard spec, not this one —
this spec's job is only to make the identity available).

### 5. Configuration (`backend/config.py`)

```python
AUTH_SECRET_KEY = os.environ.get("PROMPTSHIELD_AUTH_SECRET_KEY", "")
AUTH_TOKEN_EXPIRE_MINUTES = int(os.environ.get("PROMPTSHIELD_AUTH_TOKEN_EXPIRE_MINUTES", "60"))
AUTH_BCRYPT_ROUNDS = int(os.environ.get("PROMPTSHIELD_AUTH_BCRYPT_ROUNDS", "12"))
AUTH_LOGIN_MAX_ATTEMPTS = int(os.environ.get("PROMPTSHIELD_AUTH_LOGIN_MAX_ATTEMPTS", "5"))
AUTH_LOGIN_LOCKOUT_MINUTES = int(os.environ.get("PROMPTSHIELD_AUTH_LOGIN_LOCKOUT_MINUTES", "15"))
AUTH_DB_PATH = os.environ.get("PROMPTSHIELD_AUTH_DB_PATH", str(Path(__file__).parent / "auth" / "auth.db"))
```

Per Requirement 8.2, `app.py`/`security.py` fail fast at import time if
`AUTH_SECRET_KEY` is empty, rather than silently signing tokens with a blank/default
key.

### 6. CORS (`app.py`)

A single `CORSMiddleware` can only express one `allow_origins` policy for the whole
app it wraps (it short-circuits CORS preflight before the request ever reaches
routing), so two different policies need two separate middleware-wrapped apps, not
one shared one. `app.py` therefore mounts three sub-apps, each with its own
`CORSMiddleware`:

- `scan_app` (wildcard `allow_origins=["*"]`) — serves the existing unprefixed
  `/health`, `/analyze`, `/api/scan` paths, mounted at `"/"`.
- `auth_app` (`allow_origins=config.AUTH_ALLOWED_ORIGINS`, empty by default) — serves
  `auth_router`'s paths, mounted at `"/auth"`.
- `devices_app` (same restrictive policy) — serves `device_router`'s paths, mounted at
  `"/devices"`.

Mount registration order matters: Starlette tries mounts in the order they're added
and a `"/"` mount matches every path, so `scan_app` is mounted **last** — `/auth` and
`/devices` are tried first since they're more specific prefixes, and anything not
matching either falls through to `scan_app`. This is why `auth_router`/`device_router`
(`backend/auth/routes.py`) use paths relative to their mount prefix (`/login`, not
`/auth/login`) rather than the absolute paths shown in the endpoint table above.

## Error Handling

| Condition | Response |
|---|---|
| Missing/invalid/revoked API key on `/api/scan` | `401`, generic "invalid or missing API key" |
| Bad username or password on `/auth/login` | `401`, generic "invalid credentials" (never says which field was wrong) |
| Account locked out | `401`, generic message consistent with above (does not leak lockout state to an attacker distinctly from a wrong password — logged internally as `account_locked` for admins to see via the audit log, not exposed to the caller as a distinct HTTP status) |
| Expired/malformed JWT | `401`, "session expired, please log in again" |
| Viewer calling an admin-only route | `403` |
| `AUTH_SECRET_KEY` unset at startup | process fails to start with a clear log message (fail loud, not fail open — deliberately different from the extension's own fail-open behavior, since this is a server-side trust boundary, not a UX affordance) |

## Testing Strategy

Following this repo's existing pytest convention (direct module import, not
FastAPI TestClient/httpx — see `tests/conftest.py`):

- **`security.py`**: hash/verify round-trip; wrong password fails; token issued then
  decoded returns matching claims; expired token raises; tampered token raises.
- **`service.py`**: 
  - `authenticate_user` — correct creds succeed and reset `failed_attempts`; wrong
    creds fail and increment `failed_attempts`; 5th consecutive failure sets
    `locked_until` and a 6th attempt is rejected even with correct credentials until
    the window elapses.
  - `create_device`/`resolve_device` — freshly enrolled key resolves; revoked key does
    not; unknown key does not.
  - Every one of the above writes exactly one row to `auth_audit_log` with the correct
    `action` and `success` value — including a table-driven test asserting an
    admin-triggered `device_revoke` is logged with that admin's `actor_user_id` (this
    is the concrete test for Requirement 7's "admins are monitored too").
- **`dependencies.py`**: `require_role("admin")` passes an admin user through and
  rejects a viewer with `403`; `require_api_key` rejects a revoked/unknown key with
  `401`.
- Use a temp-file or `:memory:` SQLite DB per test (via a `pytest` fixture in
  `conftest.py`) so tests don't touch the real `auth.db` and can run in parallel.
