# Requirements Document

## Introduction

PromptShield currently has no authentication anywhere in the system: `/api/scan` accepts
requests from any origin (`allow_origins=["*"]` in `backend/app.py`), and there is no
concept of a user, device, or session (`docs/architecture.md`'s "Known architectural
gaps"). This blocks two things the team wants next: attributing each scan to a real
user/device (the audit-log/dashboard's `user_id` field), and putting a login in front
of the planned dashboard so audit history isn't world-readable.

This spec covers two independent-but-related authentication domains:

1. **Device identity** — the browser extension identifies itself to the backend on
   every `/api/scan` call via an API key, so scan events can be attributed to a device.
2. **User accounts** — the (future) dashboard requires a real login with hashed
   passwords and roles, and every security-relevant action — including actions taken
   by admin accounts — is written to an audit log, so admins are monitored, not exempt.

Out of scope for this spec: the dashboard UI itself (separate, later spec), SSO/OAuth
federation (deferred; schema leaves room for it), and any change to the browser
extension's enrollment UX beyond the API contract it calls against.

## Glossary

- **Device**: A browser-extension installation identified by a generated API key: not
  necessarily tied to a person.
- **API_Key**: A secret credential issued to a Device at enrollment, sent on every
  `/api/scan` call, hashed at rest, individually revocable.
- **User**: A person with dashboard login credentials (email/username + password) and
  a Role.
- **Role**: `admin` or `viewer` — governs which dashboard/device-management endpoints a
  User may call.
- **Access_Token**: A signed, short-lived JWT issued at login, presented on subsequent
  authenticated requests, encoding the user's id and role.
- **Auth_Audit_Log**: An append-only record of security-relevant events (login
  success/failure, device enrollment/revocation, role changes) including events
  performed by admin accounts.
- **Scan_Event**: The (separately specced) per-`/api/scan`-call audit row that a Device
  identity gets attached to; referenced here only as the consumer of Device identity.

## Requirements

### Requirement 1: Device Enrollment

**User Story:** As a browser-extension install, I want to enroll once and receive an
API key, so that subsequent scan requests can be attributed to a consistent device
identity without requiring the end user to log in every time.

#### Acceptance Criteria

1. WHEN a client calls `POST /devices/enroll` with a human-readable label, THE system
   SHALL create a new Device record and return a newly generated API_Key exactly once
   in the response body.
2. THE system SHALL store only a salted hash of the API_Key, never the plaintext value,
   so a database read alone cannot yield a usable key.
3. WHEN `POST /devices/enroll` is called with a valid Access_Token, THE system SHALL
   bind the created Device's `owner_user_id` to that token's user; WHEN called without
   one, THE system SHALL create the Device unbound (`owner_user_id = NULL`).
4. THE system SHALL record the enrollment event in the Auth_Audit_Log.

### Requirement 2: Device Authentication on Scan Requests

**User Story:** As the backend, I want to validate the API key on every scan request,
so that each Scan_Event can be attributed to the Device that sent it.

#### Acceptance Criteria

1. WHEN `POST /api/scan` is called with a valid, non-revoked API_Key (via
   `X-API-Key` header), THE system SHALL resolve it to a Device and make the device id
   (and bound user id, if any) available to the request handler.
2. WHEN `POST /api/scan` is called with a missing, malformed, unknown, or revoked
   API_Key, THE system SHALL reject the request with `401 Unauthorized` and SHALL NOT
   run the detection pipeline.
3. THE system SHALL update the Device's `last_used_at` timestamp on every successful
   validation, without this write blocking or measurably slowing the scan response.
4. THE API_Key validation SHALL add no more than 5ms to `/api/scan`'s total latency
   budget under normal operation (in-process hash lookup, no network call).

### Requirement 3: Device Revocation

**User Story:** As an admin, I want to revoke a device's API key, so that a
lost/compromised laptop or decommissioned install can no longer submit scans.

#### Acceptance Criteria

1. WHEN a User with Role `admin` calls `POST /devices/{id}/revoke`, THE system SHALL
   mark the Device revoked (set `revoked_at`) such that Requirement 2's validation
   subsequently rejects that API_Key.
2. WHEN a User with Role `viewer` (or no valid Access_Token) calls
   `POST /devices/{id}/revoke`, THE system SHALL reject with `403 Forbidden` and SHALL
   NOT revoke the Device.
3. THE system SHALL record the revocation event, including the acting admin's user id,
   in the Auth_Audit_Log.
4. Revocation SHALL be irreversible via the API (re-enrollment issues a new Device/key
   rather than un-revoking).

### Requirement 4: User Account & Password Storage

**User Story:** As a system operator, I want user credentials stored safely, so that a
database compromise doesn't directly expose passwords.

#### Acceptance Criteria

1. THE system SHALL store passwords only as a salted hash produced by a
   deliberately-slow KDF (bcrypt or equivalent), never in plaintext or reversibly
   encrypted form.
2. THE system SHALL reject account creation with a plaintext password shorter than a
   configurable minimum length (default 8).
3. Each User record SHALL have exactly one Role at a time (`admin` or `viewer`).
4. THE system SHALL provide no self-service signup endpoint in this phase; the first
   admin account is created via an offline bootstrap script, and subsequent accounts
   are created by an existing admin.

### Requirement 5: Login & Session Issuance

**User Story:** As a dashboard user, I want to log in with my credentials and receive
a token, so that I can make authenticated requests without resending my password each
time.

#### Acceptance Criteria

1. WHEN `POST /auth/login` is called with a matching username/email and password, THE
   system SHALL issue a signed Access_Token encoding the user id, role, and an
   expiration time (default 60 minutes).
2. WHEN `POST /auth/login` is called with a non-matching username or password, THE
   system SHALL respond `401 Unauthorized` with a generic error message that does not
   reveal whether the username or the password was wrong.
3. THE system SHALL record every login attempt (success and failure) in the
   Auth_Audit_Log, including the attempted username and a failure/success flag, but
   never the attempted password.
4. WHEN a User has 5 failed login attempts within a configurable window (default 15
   minutes), THE system SHALL temporarily lock that account against further login
   attempts and record the lockout in the Auth_Audit_Log.
5. WHEN `GET /auth/me` is called with a valid Access_Token, THE system SHALL return the
   caller's user id, username, and role.
6. WHEN any endpoint requiring authentication is called with a missing, malformed, or
   expired Access_Token, THE system SHALL reject with `401 Unauthorized`.

### Requirement 6: Role-Based Access Control

**User Story:** As a technical architect, I want dashboard/device-management endpoints
gated by role, so that read-only staff can't revoke keys, purge data, or manage users.

#### Acceptance Criteria

1. THE system SHALL classify every authenticated endpoint as requiring either "any
   authenticated user" or "admin" access.
2. WHEN a User with Role `viewer` calls an admin-only endpoint, THE system SHALL reject
   with `403 Forbidden`.
3. Admin-only endpoints SHALL include, at minimum: device revocation, user account
   creation/role changes, and (once built) audit-log purge/retention actions.

### Requirement 7: Auditing Admin Actions

**User Story:** As a technical architect, I want admin accounts to be monitored like
everyone else, so that no single account is a blind spot in the audit trail.

#### Acceptance Criteria

1. THE Auth_Audit_Log SHALL record the acting user id for every action it logs,
   including actions performed by `admin`-role accounts, with no exemption path.
2. THE Auth_Audit_Log SHALL be append-only via the application's normal code paths: no
   endpoint in this spec SHALL delete or edit existing Auth_Audit_Log rows.
3. THE system SHALL provide a `GET /auth/audit-log` endpoint, restricted to `admin`
   Role, to read recorded events (paginated, filterable by actor/action/date range).

### Requirement 8: Network Boundary

**User Story:** As a technical architect, I want the new authenticated endpoints to
not inherit the scan API's permissive CORS, so that adding auth doesn't quietly widen
the attack surface it's meant to shrink.

#### Acceptance Criteria

1. THE system SHALL apply a distinct, non-wildcard CORS policy to `/auth/*` and
   `/devices/*` routes, separate from `/api/scan`'s existing `allow_origins=["*"]`.
2. THE secret key used to sign Access_Tokens SHALL be read from configuration
   (environment variable / `.env`), SHALL NOT be hardcoded, and SHALL have no
   insecure default that would work in a real deployment (startup SHALL fail loudly
   if unset outside of local/dev mode).
