# Spec: Authentication

**Status: in progress.** Adds the two auth domains the team agreed on: device/API-key
identity for `/api/scan` attribution, and user accounts + JWT sessions + RBAC + an
audit log (that also covers admin actions) for the dashboard/device-management
surface. The dashboard UI and the Scan_Event audit table it will read from are a
separate, later spec — this one only makes device/user identity available for that
spec to consume.

## Documents (Kiro spec-driven workflow, requirements → design → tasks)

- **[`requirements.md`](requirements.md)** — EARS-style acceptance criteria and
  glossary (Device, API_Key, User, Role, Access_Token, Auth_Audit_Log).
- **[`design.md`](design.md)** — architecture, `backend/auth/` module layout, SQLite
  schema (`users`, `devices`, `auth_audit_log`), endpoint surface, error handling, and
  testing strategy.
- **[`tasks.md`](tasks.md)** — implementation task breakdown with a dependency graph;
  tasks are checked off (`[x]`) as they land.

## Why two identity domains instead of one

The extension talks to the backend on every keystroke's send — a login prompt there
would be pure friction for no benefit, so it gets a lightweight, generated API key
instead. The dashboard is a security/audit surface where distinguishing *people*
(especially admins, who must be monitored like anyone else, not exempted) actually
matters, so it gets real accounts. Both feed the same `auth_audit_log` table.

## If you're changing this system further

Update `requirements.md`/`design.md` first, then `tasks.md`, before editing
`backend/auth/` code directly — `tests/test_auth.py` is written against the
acceptance criteria here and will need matching updates.
