# PromptShield — Test Scenarios

Covers every rule in `rules.json`, every recognizer entity type, and
every `schema.json` field that can influence a decision. Organized so
you can tell at a glance which results are **deterministic** (Regex +
Presidio + Policy Engine - no LLM involved, exact output guaranteed)
versus **ECI-dependent** (Ollama's classification feeds into the
decision - "expected direction" is guaranteed, exact wording of
`reasoning` will vary).

**How to test:** send each `Input` as `{"text": "..."}` to `POST /analyze`
(via Swagger UI at `/docs`, or however routes.py exposes it once
reconciled with the extension - see `docs/progress-summary.md`).

---

## Section A — Deterministic (Regex + Presidio + Policy only)

These don't depend on Ollama being up or accurate - if these fail, the
bug is in `regex_engine.py`, `presidio_engine.py`, `helpers.py`, or
`policy_engine.py`/`rules.json`, not the AI layer.

### A1. ALLOW — nothing detected

| Input | Expected entityTypes | Expected riskScore | Expected decision |
|---|---|---|---|
| `Hi, how are you?` | `[]` | 0 | ALLOW |
| `` (empty string) | `[]` | 0 | ALLOW |

### A2. MASK — single PII entity per type

Each row should produce **exactly one** entity of the listed type,
`riskScore` per `risk_engine.py`'s weight table, decision `MASK` via
`mask_personal_identifiers`.

| Input | entityType | Weight | Expected riskScore | Expected decision |
|---|---|---|---|---|
| `My name is Gaurav Agrawal.` | `PERSON` | 5 | 5 | MASK |
| `My email is gaurav@example.com.` | `EMAIL_ADDRESS` | 5 | 5 | MASK |
| `My phone number is 9876543210.` | `PHONE_NUMBER` | 5 | 5 | MASK |
| `My PAN is AKMPA2899D.` | `PAN_NUMBER` | 20 | 20 | MASK |
| `My Aadhaar number is 4567 8912 3456.` | `AADHAAR_NUMBER` | 20 | 20 | MASK |
| `My passport number is Z1234567.` | `PASSPORT_NUMBER` | 20 | 20 | MASK |
| `My GSTIN is 22AAAAA0000A1Z5.` | `GSTIN` | 20 | 20 | MASK |
| `My driving license is MH1220231234567.` | `DRIVING_LICENSE` | 15 | 15 | MASK |
| `My IFSC code is HDFC0001234.` | `IFSC_CODE` | 10 | 10 | MASK |
| `My UPI ID is gaurav@oksbi.` | `UPI_ID`* | 10 | 10 | MASK |
| `My employee ID is EMP12345.` | `EMPLOYEE_ID` | 10 | 10 | MASK |
| `My vehicle number is MH12AB1234.` | `VEHICLE_NUMBER` | 5 | 5 | MASK |

\* `UPI_ID`'s pattern (`name@bank`) overlaps Presidio's built-in
`EMAIL_ADDRESS` recognizer on the same span - whichever has the higher
score wins after dedup. Either outcome still triggers MASK, so the
decision is stable even if the exact entity type isn't.

### A3. BLOCK — secrets/credentials

Each triggers `block_secret_credentials`. Note `JWT_TOKEN` alone stays
under the risk-40 threshold, so it does **not** also trigger
`warn_high_aggregate_risk` - the others do (severity resolution still
correctly picks BLOCK either way, but the `matchedRules` list differs).

| Input | entityType | riskScore | matchedRules | Decision |
|---|---|---|---|---|
| `My GitHub token is ghp_123456789012345678901234567890123456.` | `GITHUB_TOKEN` | 40 | `block_secret_credentials`, `warn_high_aggregate_risk` | BLOCK |
| `The OpenAI API key is sk-proj-7xYzAbCdEfGhIjKlMnOpQrStUvWx123456.` | `OPENAI_API_KEY` | 40 | `block_secret_credentials`, `warn_high_aggregate_risk` | BLOCK |
| `AWS access key: AKIAIOSFODNN7EXAMPLE` | `AWS_ACCESS_KEY` | 40 | `block_secret_credentials`, `warn_high_aggregate_risk` | BLOCK |
| `Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyIjoiZ2F1cmF2In0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c` | `JWT_TOKEN` | 30 | `block_secret_credentials` (only) | BLOCK |
| `-----BEGIN PRIVATE KEY-----`<br>`MIIEvQIBADANBgkqhkiG9w0BAQEFAASC...`<br>`-----END PRIVATE KEY-----` | `PRIVATE_KEY` | 50 | `block_secret_credentials`, `warn_high_aggregate_risk` | BLOCK |

### A4. Known gap — infrastructure identifiers alone → incorrectly ALLOW

**This is a real gap, not a typo.** `HOST_NAME` and `MAC_ADDRESS` aren't
in `mask_personal_identifiers`' entity list, and a single instance
(weight 10) stays well under the risk-40 WARN threshold.

| Input | entityType | riskScore | Expected (current behavior) | Should probably be |
|---|---|---|---|---|
| `Application host is db-prod.company.local.` | `HOST_NAME` | 10 | **ALLOW** | MASK or WARN |
| `Server MAC address is 00:1A:2B:3C:4D:5E.` | `MAC_ADDRESS` | 10 | **ALLOW** | MASK or WARN |

**Recommendation:** add `HOST_NAME`/`MAC_ADDRESS` to
`mask_personal_identifiers`'s entity list in `rules.json`, or create a
dedicated `warn_infrastructure_identifiers` rule. Worth a quick decision
with Gaurav before the demo.

### A5. Known gap — `BANK_ACCOUNT` is unreachable

`banking.py`'s `BANK_ACCOUNT` pattern has `score=0.50`. Even with
Presidio's maximum context-word boost (~+0.30), it tops out around
0.80 - still below `presidio_engine.py`'s `MIN_SCORE = 0.85` filter. It
will **never** actually be returned by `detect_entities()`.

| Input | Expected entityTypes | Expected decision | Note |
|---|---|---|---|
| `My bank account number is 123456789012, held at HDFC bank.` | `[]` (bug: should include `BANK_ACCOUNT`) | ALLOW | Real account numbers currently pass through undetected |

**Recommendation:** lower `BANK_ACCOUNT`'s `MIN_SCORE` exemption, raise
its base pattern score, or add stronger context words - flag to Gaurav.

### A6. Entity dedup — overlapping detections on the same span

Confirmed from real Presidio output earlier in this project: Aadhaar
numbers get double-tagged as both `AADHAAR_NUMBER` (custom recognizer,
score 0.95) and `DATE_TIME` (Presidio's generic NER, score 0.85) on the
exact same character span.

| Input | Expected entityCount | Expected entityTypes | Decision |
|---|---|---|---|
| `My Aadhaar number is 4567 8912 3456.` | **1** (not 2 - `DATE_TIME` discarded, lower score) | `["AADHAAR_NUMBER"]` | MASK |

If this shows `entityCount: 2` or both types present, `merge_detection_results()`'s dedup logic has regressed.

### A7. Combined PII — MASK still outranks WARN

| Input | Entities | riskScore | matchedRules | Decision |
|---|---|---|---|---|
| `PAN AKMPA2899D, Aadhaar 4567 8912 3456, driving license MH1220231234567.` | PAN(20)+AADHAAR(20)+DL(15) | 55 | `mask_personal_identifiers`, `warn_high_aggregate_risk` | **MASK** (not WARN - MASK outranks WARN even though risk crossed 40) |

### A8. Policy design edge case — worth a team discussion

Four PII types together cross the risk-80 **BLOCK** threshold via
`block_critical_aggregate_risk`, even though none of them individually
warrants more than masking.

| Input | Entities | riskScore | matchedRules | Decision |
|---|---|---|---|---|
| `PAN AKMPA2899D, Aadhaar 4567 8912 3456, passport Z1234567, GSTIN 22AAAAA0000A1Z5.` | PAN(20)+AADHAAR(20)+PASSPORT(20)+GSTIN(20) | **80** | `mask_personal_identifiers`, `warn_high_aggregate_risk`, `block_critical_aggregate_risk` | **BLOCK** |

**Is this the right call?** Four pieces of PII with zero secrets and
zero enterprise-architecture content getting BLOCKed (rather than
MASKed) is arguably too aggressive. Worth deciding with Gaurav whether
`block_critical_aggregate_risk`'s threshold should be raised, or
whether PII-only combinations should be excluded from the aggregate
BLOCK path entirely.

---

## Section B — ECI-dependent (requires live Ollama)

"Expected direction" is what the architecture is designed to produce,
confirmed against real runs earlier in this project. Exact `reasoning`
text will vary between runs even with `temperature: 0` due to model
nondeterminism at the token level - the **decision** should not vary.

### B1. ALLOW — public knowledge, even when a knowledge snippet is retrieved

This is the single most important test in this document - it's the
exact case that broke and got fixed earlier (model was "laundering"
facts from a retrieved snippet into its verdict).

| Input | requiresEnterpriseKnowledge | containsInternalArchitecture | Expected decision |
|---|---|---|---|
| `Explain OAuth2.` | `false` | `false` | ALLOW |
| `What's the capital of France?` | `false` | `false` | ALLOW |

**Run this one 2-3 times in a row.** If `Explain OAuth2.` flips to
`true` on any run, the reliability fix has regressed - check
`ollama_client.py`'s `temperature: 0` setting first.

### B2. BLOCK — internal architecture (confirmed via real test runs)

| Input | containsInternalArchitecture | eci confidence | riskScore (approx) | Expected decision |
|---|---|---|---|---|
| `Explain our OAuth2 implementation.` | `true` | ~0.95 | ~57 | BLOCK |
| `Why does the Mercury payment flow retry three times before failing over to the backup gateway?` | `true` | ~0.95 | ~57 | BLOCK |

### B3. WARN — requires enterprise knowledge, but not architecture/source-code specific

Harder to guarantee precisely (depends on how the model weighs
"process/business" questions vs. "architecture" questions), but should
land on WARN, not BLOCK or ALLOW, since it shouldn't trigger
`containsInternalArchitecture`/`containsSourceCode`.

| Input | Expected requiresEnterpriseKnowledge | Expected decision |
|---|---|---|
| `Who is the escalation contact if the Mercury payment flow has an outage?` | `true` | WARN (verify `containsInternalArchitecture` stays `false` - if it flips `true`, this becomes a BLOCK case instead, which is also acceptable but worth noting which one your model actually produces) |

### B4. WARN — ECI could not classify (operational test, not a prompt test)

Stop Ollama (`ollama stop` or kill the service), then send **any**
prompt.

| Condition | Expected confidence | Expected decision |
|---|---|---|
| Ollama unreachable | `0.0` | WARN, `reasoning` contains `"ECI fallback triggered"` |

This is the fail-closed path - confirm it still says WARN, not ALLOW,
when the model can't be reached at all.

---

## Section C — Real-world composite (matches actual Presidio sample data)

Gaurav's original real sample response, reused as a single realistic
composite test - exercises regex, Presidio, merge/dedup, ECI, and
policy all in one shot.

**Input:**
```
My name is Gaurav.
My GitHub token is ghp_123456789012345678901234567890123456.
My PAN is AKMPA2899D.
My Aadhaar number is 4567 8912 3456.
```

| Aspect | Expected |
|---|---|
| entityTypes | `PERSON`, `GITHUB_TOKEN`, `PAN_NUMBER`, `AADHAAR_NUMBER` |
| riskScore | 5 + 40 + 20 + 20 = **85** |
| matchedRules | `block_secret_credentials`, `mask_personal_identifiers`, `warn_high_aggregate_risk`, `block_critical_aggregate_risk` |
| Decision | **BLOCK** (secret present - correct regardless of the Section A8 aggregate-risk debate, since `GITHUB_TOKEN` alone already forces BLOCK) |

---

## Summary checklist

- [ ] A1-A3, A6-A7: run once, exact match required (no LLM variance)
- [ ] A4-A5, A8: known gaps - confirm they still reproduce, then decide whether to fix before demo
- [ ] B1: run 3x, decision must stay stable every time
- [ ] B2-B3: run once, decision direction should match
- [ ] B4: operational test, requires stopping Ollama deliberately
- [ ] Section C: single composite sanity check, exact entityTypes/riskScore, BLOCK decision
