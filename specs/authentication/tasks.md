# Implementation Plan: Authentication

## Overview

Implements `requirements.md`/`design.md`: device/API-key identity for `/api/scan`, and
user accounts + JWT sessions + RBAC + audit log for the (future) dashboard and
device-management endpoints. Browser-extension enrollment UI and the dashboard UI
itself are explicitly out of scope — this plan builds the backend capability only.

## Tasks

- [x] 1. Configuration and dependencies
  - Add `AUTH_SECRET_KEY`, `AUTH_TOKEN_EXPIRE_MINUTES`, `AUTH_BCRYPT_ROUNDS`,
    `AUTH_LOGIN_MAX_ATTEMPTS`, `AUTH_LOGIN_LOCKOUT_MINUTES`, `AUTH_DB_PATH` to
    `backend/config.py`
  - Add matching entries + comments to `backend/.env.example`
  - Add `bcrypt` and `pyjwt` to `backend/requirements.txt`
  - _Requirements: 4.1, 5.1, 8.2_

- [x] 2. Persistence layer (`backend/auth/db.py`)
  - Connection helper (`get_connection()`), schema creation for `users`, `devices`,
    `auth_audit_log` (idempotent `CREATE TABLE IF NOT EXISTS`)
  - Ensure `backend/auth/` (and the `.db` file) is git-ignored
  - _Requirements: 1.2, 4.1, 4.3, 7.2_

- [x] 3. Security primitives (`backend/auth/security.py`)
  - `hash_secret`/`verify_secret` (bcrypt, cost from `AUTH_BCRYPT_ROUNDS`)
  - `generate_api_key` (`secrets.token_urlsafe(32)`)
  - `issue_access_token`/`decode_access_token` (PyJWT, HS256, `exp` claim)
  - Fail fast at import if `AUTH_SECRET_KEY` is unset
  - _Requirements: 4.1, 5.1, 5.6, 8.2_

- [x] 4. Checkpoint - security primitives complete
  - Unit tests: hash round-trip, wrong-password rejection, token issue/decode,
    expired/tampered token rejection

- [x] 5. Pydantic schemas (`backend/auth/schemas.py`)
  - `LoginRequest`, `TokenResponse`, `UserOut`, `DeviceEnrollRequest`,
    `DeviceEnrollResponse`, `DeviceOut`, `AuditLogEntryOut`
  - _Requirements: 1.1, 5.1, 5.5, 7.3_

- [x] 6. Business logic (`backend/auth/service.py`)
  - `authenticate_user` with lockout tracking (increment/reset `failed_attempts`,
    set/check `locked_until`)
  - `create_device` (bind `owner_user_id` if a caller identity is present)
  - `resolve_device` (reject unknown/revoked keys)
  - `revoke_device`
  - `record_audit_event`, called from every path above with no exemption for admin
    actors
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 3.1, 3.3, 3.4, 4.2, 5.1, 5.2, 5.3, 5.4, 7.1, 7.2_

- [x] 7. Checkpoint - service layer complete
  - Unit tests against a temp/`:memory:` SQLite DB: correct/incorrect login, lockout
    after 5 failures, device enroll/resolve/revoke lifecycle, and an explicit
    assertion that a `device_revoke` performed by an admin writes that admin's
    `actor_user_id` to `auth_audit_log`

- [x] 8. FastAPI dependencies (`backend/auth/dependencies.py`)
  - `require_api_key` (Header `X-API-Key` -> `Device`, 401 on missing/invalid/revoked)
  - `get_current_user` (Header `Authorization: Bearer ...` -> `User`, 401 on
    missing/invalid/expired)
  - `require_role(role)` (403 if mismatched)
  - _Requirements: 2.1, 2.2, 5.6, 6.1, 6.2_

- [x] 9. Routes (`backend/auth/routes.py`)
  - `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`
  - `GET /auth/audit-log` (admin-only, paginated + filterable by actor/action/date)
  - `POST /devices/enroll`, `GET /devices` (admin-only), `POST /devices/{id}/revoke`
    (admin-only)
  - _Requirements: 1.1, 1.3, 3.1, 3.2, 5.1, 5.2, 5.5, 6.3, 7.3_

- [x] 10. Wire into the app
  - Register the auth router in `backend/app.py`
  - Add `device: Device = Depends(require_api_key)` to the existing
    `POST /api/scan` handler in `backend/routes.py` (device id available to the
    handler; persisting it onto a scan-event row is the dashboard spec's job, not
    this one)
  - Scope CORS for `/auth/*` and `/devices/*` separately from `/api/scan`'s existing
    wildcard policy
  - _Requirements: 2.1, 2.2, 8.1_

- [x] 11. Bootstrap script (`scripts/create_admin.py`)
  - CLI script to create the first `admin` user directly against `auth.db` (no
    self-service signup exists per Requirement 4.4)
  - _Requirements: 4.4_

- [x] 12. Documentation (`backend/auth/README.md`)
  - Module overview, endpoint table, config reference, "how to create the first
    admin" pointing at the bootstrap script

- [x] 13. Final checkpoint - feature complete
  - `tests/test_auth.py` (28 tests): security primitives, service-layer lifecycle +
    audit coverage, dependency guards (role check, api-key check) - all passing
  - Smoke-tested the mounted app end-to-end (enroll → scan with key → revoke →
    scan rejected; login → `/auth/me`; viewer blocked from an admin route with
    `403`; scan API preflight reflects the wildcard origin while `/auth/*`'s
    preflight does not echo an unlisted origin) - confirms the CORS-isolation
    mount ordering in `app.py` behaves as designed

## Notes

- No FastAPI `TestClient`/`httpx` dependency is introduced — tests call
  `service.py`/`security.py`/`dependencies.py` functions directly, consistent with
  this repo's existing test style (`tests/conftest.py`).
- SSO/OAuth, self-service signup, password reset, and the dashboard UI are explicitly
  deferred; `users.auth_provider`/`external_id` exist now so SSO doesn't require a
  schema migration later.

## Task Dependency Graph

```
1 (config/deps)
 └─▶ 2 (db schema) ─▶ 3 (security) ─▶ 4 (checkpoint)
                                        │
                        5 (schemas) ◀───┘
                              │
                              ▼
                        6 (service) ─▶ 7 (checkpoint)
                              │
                              ▼
                        8 (dependencies)
                              │
                              ▼
                        9 (routes) ─▶ 10 (wire into app)
                                            │
                              11 (bootstrap script) ◀┘
                                            │
                                            ▼
                                    12 (docs) ─▶ 13 (final checkpoint)
```
