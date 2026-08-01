# Implementation Plan: Audit/Dashboard Branch Consolidation

## Overview

Implements `requirements.md`/`design.md`: merge `agentic-ai-implementation` into
`audit-dashboard-dev`, resolve the three genuinely-conflicting files, re-attach
`audit_logger.py` to the current pipeline, enrich its schema, surface
`llm_provider`/`llm_model`, and reconcile the browser extension. Dashboard UI itself
is a later, separate spec.

## Tasks

- [ ] 1. Create the consolidation branch and merge
  - Local branch tracking `origin/audit-dashboard-dev`, merge in
    `origin/agentic-ai-implementation`
  - Confirm the only real conflicts are `backend/routes.py`, `backend/models.py`,
    `backend/config.py` (per design.md's divergence scoping); everything else
    resolves automatically
  - _Requirements: 1.1, 1.2, 6.2_

- [ ] 2. Resolve `backend/models.py`
  - Re-add `username`/`platform` optional fields to `ScanRequest`
  - _Requirements: 2.1, 5.1_

- [ ] 3. Resolve `backend/config.py`
  - Add `AUDIT_DB_PATH`, keep everything else from `agentic-ai-implementation`'s side
  - _Requirements: 2.1_

- [ ] 4. Surface `llm_provider`/`llm_model` (`backend/ai/llm_router.py`,
      `backend/ai/semantic_classifier.py`)
  - `route_llm_call()` returns `(response_text, provider_name)`
  - Add `PROVIDER_MODEL` lookup dict
  - `classify()` adds `_llm_provider`/`_llm_model` to its returned dict
  - _Requirements: 3.2_

- [ ] 5. Resolve `backend/routes.py`
  - Base: current pre-classifier + Smart LLM Router + `Depends(require_api_key)`
  - Re-add `log_scan()` call using current-pipeline data (`pre_result["decision_path"]`,
    `policy_result["explanation"]`, popped `_llm_provider`/`_llm_model`, `device.id`/
    `device.owner_user_id`)
  - Confirm `_llm_provider`/`_llm_model` are popped from `eci_raw` before
    `ECIResult(**eci_raw)`
  - _Requirements: 2.1, 3.1, 3.2, 3.3, 4.1_

- [ ] 6. Checkpoint - backend wiring complete
  - `python backend/audit/audit_logger.py` (manual smoke) still logs a row with the
    schema pre-enrichment, confirming nothing upstream broke before schema changes

- [ ] 7. Enrich `backend/audit/audit_logger.py` schema
  - Additive `ALTER TABLE` for `reason`, `llm_provider`, `llm_model`,
    `decision_path`, `device_id`, `owner_user_id`, each guarded against
    "column already exists"
  - `log_scan()` signature grows to accept the new fields, all defaulting to `None`
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3_

- [ ] 8. Update `tests/test_audit_logger.py`
  - New cases: row with `llm_provider` populated (ECI ran) vs `NULL` (pre-classifier
    skipped); `device_id`/`owner_user_id` populated from a fake device
  - Existing no-raw-value / never-raises / idempotent-schema assertions unchanged
  - _Requirements: 1.3, 2.2, 2.3_

- [ ] 9. Checkpoint - audit logging complete
  - `tests/test_audit_logger.py` and `tests/test_auth.py` both passing on the
    consolidated branch

- [ ] 10. Extension: device enrollment + `X-API-Key` (new — didn't exist on either
       branch)
  - `background.js` enrolls once on install, persists the key via
    `chrome.storage.local`
  - `api-client.js` attaches `X-API-Key` on every `/api/scan` call
  - _Requirements: 5.1, 5.3_

- [ ] 11. Extension: port identity capture from `audit-dashboard-dev`
  - `identity.js`, `site-definitions.js`'s `identitySelectors`, popup fallback UI -
    port as-is (confirmed no competing edits from `agentic-ai-implementation`)
  - _Requirements: 5.2, 5.3_

- [ ] 12. Final checkpoint - feature complete
  - Full test suite passes on the consolidated branch
  - Manual smoke test (real extension, real backend): enroll → scan → confirm a
    `scan_audit_log` row has `device_id`, `decision_path`, and (for an
    escalated-to-ECI prompt) `llm_provider`/`llm_model` all populated
  - Merge commit pushed to `origin/audit-dashboard-dev` as a normal merge (no
    rebase/force-push), per Requirement 6.2

## Notes

- This is deliberately a scoped merge, not a rewrite of either branch's history -
  see design.md's "Why a merge, not a repeat of PR #20."
- The dashboard UI itself is out of scope here; once this lands, `audit-dashboard-dev`
  has everything the original dashboard proposal's field list needed, and the next
  spec builds the UI against it.

## Task Dependency Graph

```
1 (branch + merge)
 ├─▶ 2 (models.py)
 ├─▶ 3 (config.py)
 └─▶ 4 (llm_provider plumbing)
       │
       ▼
     5 (routes.py) ─▶ 6 (checkpoint)
                            │
                            ▼
                      7 (schema enrichment)
                            │
                            ▼
                      8 (test_audit_logger.py) ─▶ 9 (checkpoint)
                                                        │
                              10 (extension: auth) ◀────┤
                              11 (extension: identity) ◀┘
                                            │
                                            ▼
                                    12 (final checkpoint)
```
