# Policy Engine

Deterministic, rules-based decision layer for PromptShield. It takes the merged
findings from the Presidio and ECI (Enterprise Context Intelligence) layers and
turns them into a final decision — no AI involved in the decision itself, so
the outcome is always explainable and reproducible for the same input.

## Where this sits in the pipeline

```
Regex (planned) ─┐
                  ├─→ detection {entityCount, entityTypes}
Presidio ─────────┘                                          ┌─→ decision (ALLOW/WARN/MASK/BLOCK)
                                                     decide() ─┤   explanation
ECI (backend/ai/) ──────────→ eci {schema.json shape} ────────┘   riskScore
                                                                   matchedRules
```

`backend/routes.py`'s `/api/scan` endpoint calls `decide(detection, eci)` after
running Presidio and ECI, then maps the result onto the status the browser
extension understands:

| Policy decision | Extension status | Meaning |
|---|---|---|
| `ALLOW` | `SAFE` | Sent automatically, no review popup |
| `WARN` | `SANITIZE` | Review popup shown; user can send sanitized or override |
| `MASK` | `SANITIZE` | Review popup shown; sanitized version recommended |
| `BLOCK` | `BLOCK` | Review popup shown with strongest warning; user can still "Send Anyway" |

`WARN` and `MASK` collapse to the same client-facing status because the
extension only has three states (see
`browser-extension/content/observer.js`) — the distinction between them still
shows up server-side in `matchedRules` and logs.

Regex isn't wired in yet, so `detection.entityTypes` today is Presidio-only.
Adding Regex later just means including its hits in that list before calling
`decide()` — no change needed here.

## Files

### `risk_engine.py`

Computes an aggregate **0–100 risk score** from:
- **Entity type weights** — every Presidio/Regex entity type detected
  contributes a weight (`PRIVATE_KEY` = 50, `GITHUB_TOKEN`/API keys = 40,
  government ID numbers = 20, generic PII like `EMAIL_ADDRESS`/`PERSON` = 5,
  unknown/future types default to 5 so new recognizers contribute something
  even before this list is updated).
- **ECI flags** — each true boolean flag from the ECI classification
  (`containsSecrets`, `containsInternalArchitecture`, etc.) adds its own
  weight, scaled by the model's self-reported `confidence` for that
  classification.

This score is a **supporting signal**, not the primary decision mechanism —
the explicit boolean rules in `rules.json` are. It exists so `rules.json` can
also catch cumulative risk (several medium-severity findings at once) that no
single rule would trigger on its own, and so there's an explainable number to
show in a UI/demo.

### `rules.json`

Declarative rule list consumed by `policy_engine.py`. Each rule:

```json
{
  "id": "block_secret_credentials",
  "description": "Blocked: a secret or credential (API key, token, private key) was detected.",
  "condition": { "entityTypes_any_of": ["GITHUB_TOKEN", "OPENAI_API_KEY", "..."] },
  "decision": "BLOCK"
}
```

Condition keys (all optional, combined with AND within one rule):

| Key | Matches when |
|---|---|
| `entityTypes_any_of` | Detected entity types intersect this list |
| `eci_field_true_any_of` | Any of these ECI boolean fields is `true` |
| `eci_min_confidence` | ECI's `confidence` is at least this value |
| `eci_max_confidence` | ECI's `confidence` is at most this value (used to catch low-confidence/fallback results, e.g. `warn_eci_could_not_classify`) |
| `risk_score_min` | The computed risk score is at least this value |

**Rules are OR'd, not first-match**: every rule whose condition matches is
collected, then the single highest-severity decision wins (severity order
`BLOCK > MASK > WARN > ALLOW`). This means **rule order in the file doesn't
matter**, and `matchedRules` in the response can list more than one rule ID
even though only one decision is returned.

If no rule matches, the result falls back to `rules["default_decision"]`
(currently `"ALLOW"`).

### `policy_engine.py`

`decide(detection, eci)` — the only entry point:

```python
decide(
    detection={"entityCount": 1, "entityTypes": ["GITHUB_TOKEN"]},
    eci={"requiresEnterpriseKnowledge": False, "containsInternalArchitecture": False, ...},
)
# -> {
#   "decision": "BLOCK",
#   "explanation": "Blocked: a secret or credential (API key, token, private key) was detected.",
#   "riskScore": 68,
#   "matchedRules": ["block_secret_credentials", "warn_high_aggregate_risk"]
# }
```

- `detection`: merged, deduped `{"entityCount": int, "entityTypes": [str, ...]}` from Regex + Presidio.
- `eci`: dict matching `backend/ai/schema.json` — ECI's classification.
- Does **not** include `maskedText`/`entityCount` passthrough fields in its
  return value — `routes.py` already has those and attaches them itself, so
  this module stays focused purely on the decision.

`rules.json` is read fresh on every call (no caching) — simplest correct
behavior for a rule set this small; revisit if `decide()` ever becomes a hot
path under load.

## Running standalone

```
python backend/policy/policy_engine.py
```

Runs a handful of hand-built `detection`/`eci` cases (secret detected, PII
only, enterprise architecture question, public question, ECI fallback) and
prints each decision — useful for sanity-checking rule changes without
starting the full API or touching Presidio/Ollama.

## Known limitations / next steps

- Regex layer isn't wired in yet — `detection.entityTypes` is Presidio-only.
- Rules are static and global — no per-destination (e.g. "ChatGPT vs internal
  tool") or per-user policy differentiation yet.
- No persistence/audit log of past decisions — `matchedRules`/`riskScore` are
  returned per-request and currently only surfaced via server logs and the
  API response, not stored anywhere.
