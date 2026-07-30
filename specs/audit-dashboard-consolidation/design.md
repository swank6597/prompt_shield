# Design Document: Audit/Dashboard Branch Consolidation

## Overview

Two changes, landed together on `audit-dashboard-dev`:

1. **Branch consolidation** — merge `agentic-ai-implementation` into
   `audit-dashboard-dev` as a normal merge commit, resolving the small set of files
   both branches actually touched.
2. **Audit re-attachment** — re-wire `backend/audit/audit_logger.py` (untouched
   logic, unchanged fail-safe/privacy contract) onto the current pipeline, and extend
   its schema with the fields identified as gaps against the original dashboard
   proposal.

## Why a merge, not a repeat of PR #20

PR #20 tried the same direction and was reverted (PR #21). Scoping the actual
divergence (`git diff --stat` across both branches) shows why a blind merge failed
and why a scoped one won't: of 137 changed paths, all but a handful are either (a)
pure `agentic-ai-implementation` additions with no competing edit on
`audit-dashboard-dev` (lexical/semantic engine, specs, expanded test suite,
knowledge base, `backend/auth/`), or (b) `audit-dashboard-dev`-only additions with no
competing edit on the other side (`backend/audit/`, `identity.js` and the extension
files it touches). Git resolves both of those automatically. The **only** files both
branches genuinely modified are `backend/routes.py`, `backend/models.py`, and
`backend/config.py` — three files, not 137.

`backend/regex/*.py` and two `knowledge/` files exist only on `audit-dashboard-dev`'s
older lineage: the regex files are empty post-cleanup stubs (verified by reading
them — 3-4 lines, no logic), and the knowledge files were superseded by the later
knowledge-base rebuild on `agentic-ai-implementation`. Per Requirement 1.2, the merge
takes `agentic-ai-implementation`'s side for these rather than reintroducing content
that was intentionally reorganized or was never real.

## Conflict resolution: the three real files

### `backend/routes.py`

Base structure comes from `agentic-ai-implementation` (pre-classifier + Smart LLM
Router + `Depends(require_api_key)`). Re-add, from `audit-dashboard-dev`'s version:

- The `from audit.audit_logger import log_scan` import.
- A `log_scan(...)` call at the end of `scan_prompt()`, after `policy_result` is
  computed — using data from the *current* pipeline, not the retired
  `is_trivial_prompt()`/pre-Router variables `audit-dashboard-dev`'s version read from.

```python
log_scan(
    device_id=device.id,
    owner_user_id=device.owner_user_id,
    username=request.username,
    platform=request.platform,
    masked_prompt=result["maskedText"],
    entity_count=result["entityCount"],
    entity_types=sorted(set(detection["entityTypes"])),
    eci=eci_raw,                        # llm_provider/llm_model popped before ECIResult(**eci_raw)
    reason=policy_result["explanation"],
    risk_score=policy_result["riskScore"],
    matched_rules=policy_result["matchedRules"],
    decision=policy_result["decision"],
    status=status,
    decision_path=pre_result["decision_path"] if pre_result["needs_llm"] else pre_result["decision_path"],
    llm_provider=eci_raw.pop("_llm_provider", None),
    llm_model=eci_raw.pop("_llm_model", None),
    presidio_ms=presidio_ms, eci_ms=eci_ms, policy_ms=policy_ms, total_ms=total_ms,
)
```

(`decision_path` is already computed by `pre_classify()` on the current branch and
already used in existing log lines — no new plumbing needed for that one field.)

### `backend/models.py`

Re-add `audit-dashboard-dev`'s two optional fields to `ScanRequest`:

```python
class ScanRequest(BaseModel):
    prompt: str
    username: str | None = None
    platform: str | None = None
```

Additive, non-breaking — direct Swagger/curl testing with just `{"prompt": ...}`
still works, exactly as `audit-dashboard-dev`'s own design intended.

### `backend/config.py`

Add one setting (current `config.py` otherwise wins outright — see "Why a merge" above
for why `audit-dashboard-dev`'s version of this file isn't a real alternative to
reconcile against):

```python
AUDIT_DB_PATH = os.environ.get(
    "PROMPTSHIELD_AUDIT_DB_PATH",
    os.path.join(os.path.dirname(__file__), "audit", "audit_log.db"),
)
```

## New plumbing: surfacing `llm_provider`/`llm_model`

Today, `llm_router.route_llm_call()` resolves and calls a provider but returns only
the raw response text — the provider choice is logged, never returned. One caller
(`semantic_classifier.classify()`; confirmed no other call sites). Two small changes:

1. **`llm_router.py`**: `route_llm_call()` returns `(response_text, provider_name)`
   instead of `response_text` — `provider_name` reflects whichever provider actually
   served the request (important: with `auto` strategy + fallback-to-local, this can
   differ from the initially-resolved provider if the primary failed). Add a small
   `PROVIDER_MODEL` lookup (`{"local": OLLAMA_MODEL, "groq": GROQ_MODEL, "gemini":
   GEMINI_MODEL, "bedrock": BEDROCK_MODEL_ID}`) so the caller can resolve a model
   string from the provider name without duplicating config knowledge.
2. **`semantic_classifier.classify()`**: captures `(raw, provider) =
   route_llm_call(...)`, adds `"_llm_provider": provider` and `"_llm_model":
   PROVIDER_MODEL.get(provider)` to its returned dict. Underscore-prefixed so it's
   visibly not part of the public `ai/schema.json` contract.
3. **`routes.py`**: pops both `_llm_provider`/`_llm_model` off `eci_raw` *before*
   `ECIResult(**eci_raw)` (so they never leak into the client-facing response or fail
   Pydantic validation), passes them into `log_scan()` as `llm_provider`/`llm_model`.
   When the pre-classifier skipped the LLM entirely, `eci_raw` is the
   pre-classifier's synthesized dict and has no such keys — `.pop(..., None)` handles
   that as `NULL`, matching Requirement 3.2's "or `NULL` when skipped."

## Schema changes (`backend/audit/audit_logger.py`)

Additive columns only (Requirement 3.4) — existing rows keep working, `NULL` for
columns that didn't exist when they were written:

```sql
ALTER TABLE scan_audit_log ADD COLUMN reason TEXT;
ALTER TABLE scan_audit_log ADD COLUMN llm_provider TEXT;
ALTER TABLE scan_audit_log ADD COLUMN llm_model TEXT;
ALTER TABLE scan_audit_log ADD COLUMN decision_path TEXT;
ALTER TABLE scan_audit_log ADD COLUMN device_id INTEGER;
ALTER TABLE scan_audit_log ADD COLUMN owner_user_id INTEGER;
```

Implemented as `_init_db()` attempting each `ALTER TABLE ... ADD COLUMN` and ignoring
the `sqlite3.OperationalError` raised when a column already exists (SQLite has no
`ADD COLUMN IF NOT EXISTS`) — same idempotent-across-restarts guarantee the existing
`CREATE TABLE IF NOT EXISTS` provides, extended to columns. `log_scan()`'s signature
grows to accept the four new fields (`reason`, `decision_path`, `llm_provider`/
`llm_model`, `device_id`, `owner_user_id`), all with `None` defaults so
`tests/test_audit_logger.py`'s existing calls don't need touching unless they want to
assert on the new columns.

No new index needed yet — `device_id`/`decision_path`/`llm_provider` aren't
established dashboard-query dimensions the way `timestamp`/`decision`/`platform`
already are (Requirement 4 exists to make the data available, not to predict the
dashboard's eventual query patterns).

## Dual identity (Requirement 4)

`device_id`/`owner_user_id` (from `require_api_key`, always present post-auth) and
`username`/`platform` (from `identity.js`, best-effort, defaults to `"unknown"`) are
independent columns, not a fallback chain — a dashboard can join `device_id` back to
`backend/auth/auth.db`'s `devices`/`users` tables for a trustworthy identity, or
display `username`/`platform` directly for a human-readable one, without one
mechanism's absence blocking the other's presence. (They live in separate SQLite
files — `auth.db` vs `audit_log.db` — so this is an application-level join by ID, not
a SQL foreign key across files.)

## Extension reconciliation (Requirement 5)

Two independent additions to the extension, verified not to conflict (no shared
functions/files touched by both):

- **From this session's auth work (new)**: `background.js` enrolls a device once
  (`POST /devices/enroll`) on install, persists the returned API key in
  `chrome.storage.local`, and attaches `X-API-Key` on every `/api/scan` call via
  `api-client.js`. This did not exist on either branch before now.
- **From `audit-dashboard-dev` (port as-is)**: `identity.js`, the `identitySelectors`
  additions in `site-definitions.js`, and the popup fallback UI — unchanged, since
  `agentic-ai-implementation` never touched these files (confirmed: zero diff on
  `browser-extension/content/identity.js` and friends between the merge-base and
  `agentic-ai-implementation`'s tip).

## Testing Strategy

- `tests/test_audit_logger.py` (ported from `audit-dashboard-dev`) — extended with
  cases for the new columns (a row with a real `llm_provider` when ECI actually ran,
  `NULL` when the pre-classifier skipped it; `device_id` populated from a fake
  device id) — keeps the existing no-raw-value/never-raises/idempotent-schema
  assertions unchanged.
- `tests/test_auth.py` — unaffected by this change, re-run to confirm the merge
  didn't disturb it.
- Manual smoke test (mirrors `specs/authentication/`'s): enroll a device, scan with
  its key, confirm a `scan_audit_log` row has `device_id` set, `decision_path`
  populated, and `llm_provider`/`llm_model` populated only when the prompt actually
  escalated to ECI.
