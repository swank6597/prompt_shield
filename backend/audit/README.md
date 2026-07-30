# Audit Logger

Persists a privacy-safe record of every `/api/scan` decision to SQLite, so
there's a queryable trail for compliance review and the future dashboard
(counts by decision/day/platform). No AI, no decision-making here — this is
a pure write-path that runs *after* the Policy Engine has already decided.

## The one rule this module exists to enforce

**Never store the raw prompt, and never store a raw matched value.**

- `masked_prompt` is Presidio's already-anonymized output (`result[
  "maskedText"]`) — never `request.prompt`.
- `entity_types` is a JSON array of type strings only (e.g.
  `["EMAIL_ADDRESS", "GITHUB_TOKEN"]`) — never `entities[].value`, the raw
  matched value the live `/api/scan` response's `issues` list uses for the
  extension popup's "Detected Issues" display. That list is intentionally
  scoped to the ephemeral HTTP response the popup shows once; it never
  reaches this module.

`routes.py`'s existing `detection = {"entityCount": ..., "entityTypes":
[...]}` construction already discards values this same way for
`policy_engine.decide()` — this module just extends that same discipline to
persistence.

## Known limitation — read before treating this as an absolute guarantee

This guarantee is bounded by **Presidio's recall**, not perfect:

1. `presidio/presidio_engine.py`'s `MIN_SCORE = 0.85` filter drops any
   detection below that score *before* anonymization runs — a low-confidence
   true positive is never masked, so its raw text is still sitting in
   `maskedText` verbatim.
2. Any entity type no recognizer knows how to match at all (a novel secret
   format, an internal project codename, non-English PII) is invisible to
   the whole pipeline — masked or not.

Today, before this module existed, that residual risk was *ephemeral* — it
only ever lived in one HTTP response to the extension. Now that scans are
persisted, an under-detected value becomes a **standing record** in a
compliance database instead of a one-off miss. This isn't something
`audit_logger.py` can fix (it's a Presidio recall problem, not a logging
problem) — it's a real, accepted trade-off worth keeping in mind, not a
promise that everything in `masked_prompt` is guaranteed sanitized.

The same caveat applies one step further: `eci_reasoning` is LLM-generated
from `maskedText`, so if a value slips past Presidio as above, the model
could in principle quote it back in a reasoning bullet — same root cause,
same caveat, no separate fix needed.

## Schema

Single table, `scan_audit_log`, in a SQLite file at `AUDIT_DB_PATH`
(`backend/config.py`, default `backend/audit/audit_log.db`, overridable via
`PROMPTSHIELD_AUDIT_DB_PATH`). One row per `/api/scan` call.

| Column | Notes |
|---|---|
| `id` | Autoincrement PK |
| `timestamp` | ISO-8601 UTC string — sorts/ranges correctly as text |
| `username`, `platform` | `NOT NULL DEFAULT 'unknown'` — see below |
| `masked_prompt` | Presidio output only, never raw |
| `entity_count`, `entity_types` (JSON) | Types only, never values |
| `eci_intent`, `eci_document_type`, `eci_confidence` | From `ai/schema.json` |
| `eci_requires_enterprise_knowledge` ... `eci_impacts_iso27001` | One `INTEGER` (0/1) column per ECI boolean flag — kept as real columns, not a JSON blob, because these are exactly what a dashboard filters/groups by (`WHERE eci_contains_secrets = 1`, `GROUP BY eci_intent`) |
| `eci_reasoning` (JSON) | Display-only, not a filter target — stays JSON |
| `risk_score`, `matched_rules` (JSON) | From `policy_engine.decide()` |
| `decision` | Internal ALLOW/WARN/MASK/BLOCK |
| `status` | Extension-facing SAFE/SANITIZE/BLOCK — stored separately from `decision` since WARN and MASK both collapse to SANITIZE; a dashboard likely wants both granularities |
| `presidio_ms`, `eci_ms`, `policy_ms`, `total_ms` | Perf breakdown, already computed as local timers in `routes.py` |
| `reason` | `policy_result["explanation"]` — the human-readable reason behind `decision`, alongside the machine-readable `matched_rules` |
| `llm_provider`, `llm_model` | Which Smart LLM Router provider/model actually served the request (`local`/`groq`/`gemini`/`bedrock` + its configured model) — `NULL` when the pre-classifier skipped the LLM entirely |
| `decision_path` | The pre-classifier's routing label (`trivial`, `hard_block`, `pii_only`, `enterprise_detected`, `true_ambiguity`, etc. — see `ai/pre_classifier.py`) |
| `device_id`, `owner_user_id` | The **authenticated** identity from `backend/auth/` (`require_api_key`) — see "Dual identity" below |

Indexed on `timestamp`, `decision`, `platform` — the three dimensions a
dashboard aggregates by (counts by day/decision/platform). No index yet on
`device_id`/`decision_path`/`llm_provider`; add one later if a concrete
dashboard query needs it — these aren't established query dimensions the
way the indexed three already are.

`reason`/`llm_provider`/`llm_model`/`decision_path`/`device_id`/
`owner_user_id` were added via additive `ALTER TABLE ... ADD COLUMN`
(`_init_db()`, guarding against "column already exists" since SQLite has no
`ADD COLUMN IF NOT EXISTS`) — existing rows from before this change simply
have `NULL` in these columns, nothing is migrated or backfilled.

No child tables / normalization — over-engineering for a single-writer audit
log at this scale.

## Dual identity: `device_id`/`owner_user_id` vs. `username`/`platform`

Two independent identity mechanisms, not a fallback chain:

- **`device_id`/`owner_user_id`** — the API-key-authenticated device (and its
  bound user account, if any) from `backend/auth/`. Trustworthy: a request
  can't reach `log_scan()` at all without a valid, non-revoked key
  (`require_api_key` in `routes.py`). Join back to `backend/auth/auth.db`'s
  `devices`/`users` tables (a separate SQLite file — this is an
  application-level join, not a SQL foreign key) for a verified identity.
- **`username`/`platform`** — the best-effort, human-readable identity
  described below. Not authenticated; can be `"unknown"`.

A dashboard can use either independently: `device_id` for a trustworthy
audit trail, `username`/`platform` for a readable one — see
`specs/audit-dashboard-consolidation/design.md`.

## `username` / `platform`

Populated by the browser extension, sent as optional fields on `ScanRequest`
(`{"prompt": ..., "username": ..., "platform": ...}`). Both are `None` by
default (so direct Swagger/curl testing with just `{"prompt": "..."}` still
works) — `log_scan()` coalesces a missing value to `"unknown"` itself, so
that policy lives in one place.

`platform` is simply the AI site's display name (`"ChatGPT"`, `"Gemini"`,
etc. — `site.label` in `browser-extension/content/site-definitions.js`).
`username` is best-effort: the extension auto-detects the account name/email
already visible on the page (no simulated clicks), falling back to a value
the user enters once in the extension popup if detection finds nothing. See
`browser-extension/content/identity.js`.

## Fail-safe contract

`log_scan()` **never raises** — matches `ai/semantic_classifier.py`'s
`classify()` contract exactly. Any failure (disk full, locked file,
permissions) is caught, logged as a `WARNING` via `get_logger("audit")`, and
swallowed. `routes.py` calls it with no try/except, same as it calls
`classify_context(...)` bare. An audit-logging failure must never turn a
working scan into a 500.

Table creation (`CREATE TABLE IF NOT EXISTS` + indexes) runs once at import
time, matching `presidio_engine.py`'s module-level-side-effect pattern —
idempotent across restarts, never wipes existing rows.

Each `log_scan()` call opens its own short-lived `sqlite3.connect(...)`
rather than sharing one module-level connection — FastAPI/uvicorn runs sync
`def` endpoints in a thread pool, and `sqlite3` connections aren't safe to
share across threads without extra locking. Negligible cost at this write
rate (one write per scan, not a hot loop).

## Running standalone

```
python backend/audit/audit_logger.py
```

Logs one hardcoded test row and prints the DB path — useful for confirming
the schema/insert work without starting the full API.
