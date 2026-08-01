# Authentication

Two independent identity mechanisms, sharing one SQLite database
(`backend/auth/auth.db`, git-ignored) and one audit log. Full design rationale in
[`specs/authentication/`](../../specs/authentication/); this file is the quick
reference for working in this module day-to-day.

## Where this sits

```
Browser Extension                         backend/routes.py
┌──────────────┐  X-API-Key header  ┌───────────────────────────────┐
│ every scan   │───────────────────▶│ POST /api/scan                │
└──────────────┘                    │   Depends(require_api_key)    │
                                     │   -> device.id / owner_user_id│
                                     └───────────────────────────────┘

Dashboard (future)   Authorization: Bearer <JWT>   backend/auth/routes.py
┌──────────────┐───────────────────▶│ POST /auth/login               │
│ login form   │                    │ GET  /auth/me                  │
└──────────────┘                    │ GET  /auth/audit-log   (admin) │
                                     │ POST /devices/enroll           │
                                     │ GET  /devices           (admin)│
                                     │ POST /devices/{id}/revoke (admin)│
                                     └────────────────────────────────┘
```

- **Device identity** (`X-API-Key`) attributes `/api/scan` calls to a browser-extension
  install. No login involved - see Requirements 1-3 in `specs/authentication/`.
- **User accounts** (bearer JWT from `/auth/login`) gate the dashboard/device-management
  surface. Roles are `admin` and `viewer`; only `admin` can revoke devices, list
  devices, or read the audit log.
- **`auth_audit_log`** records every login attempt, lockout, device enrollment, and
  device revocation - including actions taken by `admin` accounts. There is no
  exemption path; see Requirement 7.

## Module layout

| File | Responsibility |
|---|---|
| `db.py` | SQLite connection + schema (`users`, `devices`, `auth_audit_log`) |
| `security.py` | bcrypt hashing, JWT issue/decode - the only file that imports `bcrypt`/`jwt` |
| `schemas.py` | Pydantic request/response models |
| `service.py` | Business logic: login + lockout, device lifecycle, audit writes |
| `dependencies.py` | FastAPI `Depends` guards: `require_api_key`, `get_current_user`, `require_role` |
| `routes.py` | `auth_router` (`/login`, `/logout`, `/me`, `/audit-log`) and `device_router` (`/enroll`, list, `/{id}/revoke`) - mounted at `/auth` and `/devices` respectively in `backend/app.py`, each with its own CORS policy |

## Getting started locally

1. Generate a secret and add it to `backend/.env`:
   ```
   python -c "import secrets; print(secrets.token_urlsafe(32))"        
   ```
   `backend/auth/security.py` raises `RuntimeError` at import time if
   `PROMPTSHIELD_AUTH_SECRET_KEY` is unset - the backend will not start silently
   insecure.
2. Create the first admin account (no self-service signup exists by design):
   ```
   python scripts/create_admin.py --username you --role admin
   ```
3. Log in and enroll a device:
   ```
   POST /auth/login    {"username": "you", "password": "..."}   -> accessToken
   POST /devices/enroll {"label": "my-laptop"}                  -> apiKey (shown once)
   ```
4. Use the `apiKey` as `X-API-Key` on `/api/scan` requests.

### Same thing, via Swagger UI instead of curl

There is no single shared Swagger page - `/auth/login` lives on
`http://localhost:8081/auth/docs`, `/devices/enroll` on
`http://localhost:8081/devices/docs`, and `/api/scan` on plain
`http://localhost:8081/docs`. Each is its own mounted sub-app with its own
OpenAPI schema (see `app.py`'s CORS comment for why), so:

1. Open `/auth/docs`, run `POST /login`, copy `accessToken` from the response.
2. Click 🔒 **Authorize** on that same page and paste the token (no `Bearer `
   prefix needed - it's a real `HTTPBearer` security scheme).
3. Open `/devices/docs` - a **separate page with its own auth state** -
   authorizing on `/auth/docs` in step 2 does not carry over here. Click
   🔒 **Authorize** again and paste the same `accessToken`, *then* run
   `POST /enroll`, so the device gets linked to your account
   (`ownerUserId`) instead of created anonymously.
4. Copy `apiKey` from the response - shown once, not retrievable again.
5. To try `/api/scan` itself, open `/docs`, click 🔒 **Authorize**, and paste
   the `apiKey` into the `X-API-Key` field.

## Known limitations (intentional, see `specs/authentication/design.md`)

- `resolve_device()` is an O(n) bcrypt-compare over active devices, not an indexed
  lookup (bcrypt hashes aren't index-friendly). Fine at this project's scale; if
  device count grows large, switch the lookup key to a fast indexable hash while
  keeping bcrypt for password storage specifically.
- Sessions are stateless JWTs - there's no server-side revocation list, so
  `/auth/logout` only records intent in the audit log; a leaked token remains valid
  until it expires (`PROMPTSHIELD_AUTH_TOKEN_EXPIRE_MINUTES`, default 60).
- No self-service signup, password reset, or SSO/OAuth. `users.auth_provider`/
  `external_id` exist now so SSO can slot in later without a schema migration.
- The dashboard UI itself and the scan-event audit table it will read from are a
  separate, later spec - this module only makes device/user identity available for
  that spec to consume.
