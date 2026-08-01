# Spec: Audit/Dashboard Branch Consolidation

**Status: in progress.** Merges `agentic-ai-implementation` (lexical/semantic
pre-classifier, Smart LLM Router, `backend/auth/`) into `audit-dashboard-dev`
(SQLite audit trail, browser-extension identity capture), re-attaches the audit
logger to the current pipeline instead of the older one it was built against, and
enriches its schema. `audit-dashboard-dev` becomes the branch dashboard work
continues on.

## Documents (Kiro spec-driven workflow, requirements → design → tasks)

- **[`requirements.md`](requirements.md)** — EARS-style acceptance criteria and
  glossary (Consolidated_Branch, Scan_Audit_Log, Device_Identity, Display_Identity,
  Decision_Path).
- **[`design.md`](design.md)** — why this is a scoped merge rather than a repeat of
  the reverted PR #20, the three files that actually conflict, the new
  `llm_provider`/`llm_model` plumbing, schema enrichment, and extension
  reconciliation.
- **[`tasks.md`](tasks.md)** — implementation task breakdown with a dependency graph.

## Why the previous merge attempt (PR #20) failed and this one won't

That attempt merged the two branches wholesale. Scoping the actual diff shows only
three files were genuinely edited on both sides (`backend/routes.py`,
`backend/models.py`, `backend/config.py`) — everything else is a pure addition on one
side with nothing competing on the other, which Git resolves automatically. See
design.md's "Why a merge, not a repeat of PR #20" for the full breakdown.

## Relationship to other specs

- **[`../authentication/`](../authentication/)** — the device/user identity model
  this spec attaches to the audit trail (`device_id`/`owner_user_id` columns).
- **[`../lexical-semantic-upgrade/`](../lexical-semantic-upgrade/)** — the
  pre-classifier this spec's `decision_path` column reads from.
- The dashboard UI itself is a follow-up spec, written once this one lands and
  `audit-dashboard-dev` has a complete, queryable audit trail to build against.
