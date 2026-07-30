# Requirements Document

## Introduction

Two branches diverged: `agentic-ai-implementation` gained the three-tier lexical/
semantic pre-classifier, the Smart LLM Router (multi-provider), an expanded knowledge
base, and (this session) device/user authentication — while `audit-dashboard-dev`
independently gained a SQLite audit trail (`backend/audit/audit_logger.py`) and a
browser-extension identity-capture feature (`identity.js`), built against an earlier
version of the pipeline. A prior attempt to merge the former into the latter (PR #20)
was reverted (PR #21) due to the resulting conflicts.

This spec consolidates all of `agentic-ai-implementation`'s code onto
`audit-dashboard-dev`, re-attaches the audit-logging feature to the current pipeline
(rather than the older one it was built against), enriches the audit schema to close
gaps identified against the original dashboard field list (Prompt/Decision/Reason/LLM
Used/Layer/User/Timestamp), and establishes `audit-dashboard-dev` as the branch where
dashboard-related work continues going forward.

Out of scope: the dashboard UI/frontend itself (a later spec, once this branch has a
complete, queryable audit trail to build against).

## Glossary

- **Consolidated_Branch**: `audit-dashboard-dev` after this spec — contains full
  `agentic-ai-implementation` parity plus the audit/identity features below.
- **Scan_Audit_Log**: the `scan_audit_log` SQLite table (`backend/audit/`), one row
  per `/api/scan` call.
- **Device_Identity**: the API-key-authenticated device/user from
  `specs/authentication/` (`backend/auth/`) — added this session, did not exist when
  `audit-dashboard-dev` built its audit logger.
- **Display_Identity**: the best-effort `username`/`platform` pair captured by
  `browser-extension/content/identity.js` — human-readable, not authenticated.
- **Decision_Path**: the pre-classifier's routing label (trivial / secret-skip /
  lexical-public / lexical-enterprise / semantic-skip / true-ambiguity) — exists on
  `agentic-ai-implementation`'s pipeline, did not exist when the audit logger was
  built against the older `is_trivial_prompt()` gate.

## Requirements

### Requirement 1: Full code parity on the consolidated branch

**User Story:** As the team, I want `audit-dashboard-dev` to contain everything
`agentic-ai-implementation` has, so dashboard work isn't built against a stale
pipeline a second time.

#### Acceptance Criteria

1. THE Consolidated_Branch SHALL contain the three-tier lexical/semantic
   pre-classifier, the Smart LLM Router, the expanded `knowledge/` base, and the
   `backend/auth/` authentication module exactly as they exist on
   `agentic-ai-implementation`.
2. WHERE a file exists only on `audit-dashboard-dev`'s older lineage with no
   corresponding functional change on `agentic-ai-implementation` (e.g. the emptied
   `backend/regex/` stub files, superseded `knowledge/` entries reorganized during the
   knowledge-base rebuild), THE consolidation SHALL prefer `agentic-ai-implementation`'s
   version rather than reintroducing the superseded one.
3. THE Consolidated_Branch's test suite (existing `agentic-ai-implementation` tests
   plus `tests/test_auth.py` plus `tests/test_audit_logger.py`) SHALL pass.

### Requirement 2: Audit logging re-attached to the current pipeline

**User Story:** As a compliance reviewer, I want every `/api/scan` decision on the
consolidated branch persisted to the audit trail, using the actual pipeline that ran
(pre-classifier + Smart LLM Router), not the older gate the logger was originally
wired against.

#### Acceptance Criteria

1. WHEN `/api/scan` completes on the Consolidated_Branch, THE system SHALL call
   `log_scan()` with data reflecting the pre-classifier/Smart-LLM-Router pipeline that
   actually ran, not the retired `is_trivial_prompt()` gate.
2. THE Scan_Audit_Log SHALL preserve `audit_logger.py`'s existing fail-safe contract:
   `log_scan()` SHALL NOT raise, and a logging failure SHALL NOT alter `/api/scan`'s
   HTTP response.
3. THE Scan_Audit_Log SHALL preserve the existing privacy guarantee: only the
   Presidio-masked prompt and entity *types* are stored, never the raw prompt or a raw
   matched value.

### Requirement 3: Audit schema enrichment

**User Story:** As someone building the dashboard next, I want the audit row to carry
the fields the original dashboard proposal called out as gaps, so the dashboard spec
doesn't have to re-derive them from logs.

#### Acceptance Criteria

1. THE Scan_Audit_Log SHALL gain a `reason` column populated from
   `policy_result["explanation"]`.
2. THE Scan_Audit_Log SHALL gain `llm_provider` and `llm_model` columns, populated
   from the Smart LLM Router's actual provider/model selection for that request (or
   `NULL` when the pre-classifier skipped the LLM entirely).
3. THE Scan_Audit_Log SHALL gain a `decision_path` column populated from the
   pre-classifier's routing label (Decision_Path).
4. Adding these columns SHALL NOT require dropping or migrating existing rows —
   additive `ALTER TABLE` / `CREATE TABLE IF NOT EXISTS` semantics only, consistent
   with `audit_logger.py`'s existing idempotent-schema pattern.

### Requirement 4: Dual identity — device (authenticated) and display (human-readable)

**User Story:** As a technical architect, I want both the authenticated device/user
and the best-effort human-readable identity captured per scan, since they answer
different questions (who can we trust this was vs. who does this look like it was).

#### Acceptance Criteria

1. THE Scan_Audit_Log SHALL gain nullable `device_id` and `owner_user_id` columns,
   populated from the Device_Identity resolved by `require_api_key` on that request.
2. THE Scan_Audit_Log SHALL retain its existing `username`/`platform` columns
   (Display_Identity), populated exactly as `audit_logger.py` already does — best
   effort, defaulting to `"unknown"`, never blocking a scan if absent.
3. Neither identity mechanism SHALL be a prerequisite for the other: a request with a
   valid API key but no Display_Identity (e.g. a direct API caller) SHALL still be
   logged with `device_id` populated and `username`/`platform` as `"unknown"`, and
   vice versa is not possible post-auth since `require_api_key` is mandatory on
   `/api/scan` — but the column design SHALL NOT assume both are always present.

### Requirement 5: Browser extension reconciliation

**User Story:** As an extension user, I want the extension to both identify itself
(device API key, from this session's auth work) and capture display identity (from
`audit-dashboard-dev`'s `identity.js`), since `/api/scan` now requires the former and
the audit trail wants the latter.

#### Acceptance Criteria

1. THE extension SHALL enroll a device and attach `X-API-Key` on every `/api/scan`
   call (existing gap noted in `specs/authentication/` — the extension side was not
   built in that spec).
2. THE extension SHALL continue to attempt Display_Identity auto-detection via
   `identity.js` on sites with verified selectors, falling back to the manually-entered
   popup value exactly as already implemented on `audit-dashboard-dev`.
3. THIS requirement's acceptance criteria 1 and 2 SHALL be implemented as independent,
   non-conflicting changes to the extension (they touch different files/functions),
   verified by confirming neither breaks the other's existing tests/manual checks.

### Requirement 6: `audit-dashboard-dev` becomes the branch for dashboard work

**User Story:** As the team, I want a single branch where dashboard-related work
continues, so effort doesn't split across two diverging lineages again.

#### Acceptance Criteria

1. Following this spec's completion, THE team SHALL treat `audit-dashboard-dev` as
   the base branch for the dashboard UI spec and implementation that follows.
2. THE consolidation SHALL be landed as a normal merge commit (preserving both
   branches' history), not a rebase or history rewrite, so prior work on either
   branch remains traceable.
