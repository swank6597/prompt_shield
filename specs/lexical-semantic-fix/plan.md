# Remediation Plan: Classification Accuracy Fixes

Status: proposed, awaiting approval
Scope: `backend/ai/lexical_engine.py`, `backend/ai/pre_classifier.py`,
`backend/presidio/presidio_engine.py`, `backend/ai/prompts/system_prompt.md`,
`browser-extension/interstitial/review.js`, `browser-extension/content/modal.js`

## Overview

The test suite in `tests/PromptShield_TestSuite.xlsx` reports false positives on
generic prompts: general-knowledge questions about compliance frameworks and
business processes return SANITIZE or BLOCK where ALLOW is expected.

Instrumented measurement against the running code shows this is not a threshold
calibration problem. The lexical TF-IDF score is anti-correlated with the suite's
ground truth: prompts expected to be allowed rank *higher* than prompts expected
to be blocked. No threshold value can separate them.

This plan fixes the scoring defect, removes the fast path that converts a noisy
score into an unreviewable BLOCK, closes a BLOCK bypass in the extension, and
suppresses a Presidio false positive.

## Measured Evidence

All numbers below were produced by running the actual modules against the real
48-document knowledge corpus and the official test suite. The five
secret-credential cases (#1, #2, #3, #6, #7) are excluded from scoring analysis
because Presidio catches them regardless of lexical score.

### Finding 1: the lexical score points the wrong way

```
expected BLOCK: #8 0.310   #5 0.284   #4 0.216
expected ALLOW: #9 0.720   #14 0.442  #15 0.436  #13 0.339
                #12 0.303  #10 0.278  #11 0.266

AUC = 0.238        (0.5 = coin flip; below 0.5 = actively inverted)
separation gap = -0.504
```

AUC here is the probability that a randomly chosen expected-BLOCK prompt scores
above a randomly chosen expected-ALLOW prompt. At 0.238 the signal is worse than
random. A positive separation gap is required for any single threshold to work.

Reproducible instance, case #9, the most explicitly generic prompt in the suite:

```
"In general terms, how does an OAuth 2.0 client_credentials grant work
 for service-to-service authentication?"          expected: ALLOW

lexical = 0.7200 -> ENTERPRISE_LIKELY -> LLM SKIPPED
  -> _build_enterprise_eci() hardcodes confidence=0.9,
     containsInternalArchitecture=True
  -> policy: BLOCK, risk=54
     matchedRules=[block_internal_architecture_or_code,
                   warn_requires_enterprise_knowledge,
                   warn_high_aggregate_risk]
```

`Explain OAuth2.` scores 0.5000 and blocks by the same path. That is the
canonical PUBLIC example in `system_prompt.md`, so the LLM never sees the exact
case that prompt guidance was written for.

### Finding 2: normalization is a density measure, inverted by prompt length

In `LexicalEngine.score()`:

```python
max_score = sum(tf * max_idf for tf in prompt_tf.values())  # scales with token count
normalized_score = min(raw_score / max_score, 1.0)
```

Every token inflates the denominator; only corpus-matching tokens raise the
numerator. Holding content constant and adding words lowers the score:

```
 5 tok  "What does Mercury Payments depend on?"            0.5562  ENTERPRISE_LIKELY
 7 tok  "At a high level, what does Mercury Payments...?"  0.4981  ENTERPRISE_LIKELY
10 tok  (same, one more clause)                            0.4845  ENTERPRISE_LIKELY
22 tok  (same question, fully expanded)                    0.3567  AMBIGUOUS
```

Consequence: suite case #4 (Mercury authorization pipeline, Orion Identity,
Token Vault, Merchant Registry, 12 genuine enterprise term matches) scores
**0.2122**, below `What is GDPR?` at **1.0000**.

This also produces behavior that appears random to users. The typed variant
"what does Mercury Payments depend on?" scores 0.4981 and hard-blocks, while the
suite's longer wording of the same question scores 0.4423 and routes to the LLM.
Rephrasing slightly longer changes the outcome.

### Finding 3: IDF over 48 declarative documents cannot identify internal jargon

The corpus is specs and runbooks, so interrogatives are rare in it and therefore
score as high-signal terms:

```
what     df=1/48   idf=3.8712   <- max IDF, same as rarest enterprise term
how      df=1/48   idf=3.8712
doc      df=1/48   idf=3.8712
does     df=2/48   idf=3.1781
mercury            idf=0.5390   <- actual product name, ~7x lower
```

`What is GDPR?` reaches **1.0000**, the theoretical maximum, because both
surviving tokens sit at max IDF. The `high_df_cutoff = 0.60` dampening only
fires above 29 of 48 documents, so it suppresses "the" and "and" and little
else: 15 of 29 sampled stopwords still carry nonzero IDF.

### Finding 4: adding stopwords alone makes the reported symptoms worse

Tested as an isolated change, keeping the existing normalization:

```
                              AUC     separation gap
current                       0.238      -0.504
+ stopwords only              0.381      -0.511   still inverted, gap worse
```

Mechanically, stopwords contribute nothing to the numerator but do inflate the
denominator, so removing them *raises* the ratio. Case #13 (GDPR/PCI/ISO,
expected ALLOW) regresses from AMBIGUOUS 0.339 to **ENTERPRISE_LIKELY 0.477**,
crossing from LLM review into hardcoded BLOCK. `Explain OAuth2.` moves 0.5 to
1.0.

Both changes are required together:

```
stopwords + magnitude normalization    AUC 1.000   gap +0.21   separated
normalization alone (no stopwords)     AUC 0.857   gap -7.61   #9 still ranks #1
stopwords alone                        AUC 0.381   gap -0.51   inverted
```

Caveat on the 1.000: the margin is thin (#4 BLOCK at raw 14.92 vs #15 ALLOW at
raw 14.71, roughly 1.4%). It held in all 10 leave-one-out folds, and
`raw/(raw+K)` is monotonic in `raw` so the ranking is not K-tuned. With 3 BLOCK
and 7 ALLOW cases this validates the *direction* of the fix, not final threshold
values. Threshold calibration needs a larger labelled set (see Task 8).

### Finding 5: the semantic tier does not run

In the interpreter that actually serves the backend:

```
presidio_analyzer      INSTALLED
en_core_web_lg         LOADED
sentence_transformers  MISSING
faiss                  MISSING
torch                  MISSING
```

Every scan logs `SemanticEngine unavailable`. The three-tier design runs as two
tiers, so `HYBRID_*` settings in `config.py` are inert and the second opinion
intended to catch lexical misfires never executes. `requirements.txt` pins both
packages, so this is an install gap rather than a design gap.

Related: `backend/venv` is missing `pyvenv.cfg` and is non-functional despite
`start-backend.ps1` targeting it. The backend is running on system Python 3.14.

### Finding 6: a BLOCK can be bypassed via Send Sanitized

`browser-extension/interstitial/review.js`:

```js
btnSendOriginal.hidden = status === "BLOCK";      // correctly gated
btnSendSanitized.hidden = !hasSanitizedChanges;   // NOT gated on BLOCK
```

For suite case #4 the only masking Presidio applies is the false positive
`Token Vault` -> `<PERSON>`. On a BLOCK, Send Sanitized therefore stays enabled
and transmits the full internal-architecture prompt with one product name
swapped. This is a correctness and security defect, not a cosmetic one.

### Finding 7: Presidio flags a product name as a person

```
"...routes a transaction through Orion Identity, Token Vault, and Merchant Registry."
  RAW: PERSON  score=0.85  value='Token Vault'
```

The span is `Token Vault`, not `Token`, at score exactly **0.85** — identical to
the real name `Rajesh Kumar` in a control case. Raising `MIN_SCORE` would remove
all PERSON detection, so an allowlist is the only viable approach. Blast radius
is narrow: `Orion Identity`, `Merchant Registry`, `Atlas Core`, and
`Nexus Gateway` each produce zero detections.

### Finding 8: correct blocks can render an empty issues panel

`routes.py` builds `issues` exclusively from Presidio entities. Suite case #8
blocks correctly with `entityCount=0`, so `issues=[]` and the UI renders
"No specific issue details were returned by the scanner." The reason for the
block lives in ECI flags that the issues list never reads.

## Failure Attribution

Which layer is responsible for each observed failure. This matters because the
fixes are independent and land in different files.

| Case | Symptom | Actual path taken | Responsible layer |
|------|---------|-------------------|-------------------|
| #9 | BLOCK, expected ALLOW | `enterprise_detected`, LLM skipped | lexical scoring (Tasks 1, 2) |
| #14 | BLOCK on shorter phrasing | `enterprise_detected` at 0.4981 | lexical scoring (Tasks 1, 2) |
| #12 | SANITIZE, expected ALLOW | `true_ambiguity` -> LLM | LLM judgment (Task 6) |
| #13 | SANITIZE, expected ALLOW | `true_ambiguity` -> LLM | LLM judgment (Task 6) |
| #4 | BLOCK correct, `PERSON: Token Vault` shown | `true_ambiguity` -> LLM | Presidio NER (Task 5) |
| #4 | Send Sanitized offered on BLOCK | extension | extension gating (Task 4) |
| #8 | BLOCK correct, empty issues panel | `true_ambiguity` -> LLM | response shape (Task 7) |

Cases #12 and #13 do reach the LLM today and it returns
`requiresEnterpriseKnowledge: true` at high confidence, producing WARN ->
SANITIZE. That is a genuine prompt-tuning gap, but it is currently masked by the
scoring defects, so it is sequenced after them.

## Tasks

- [x] 1. Fix lexical scoring: normalization and stopwords as a single change
  - **Ship both halves together.** Either half alone regresses suite cases
    (Finding 4). This is one atomic change, not two.
  - [x] 1.1 Replace length-normalization in `LexicalEngine.score()`
    - Remove `max_score = sum(tf * max_idf ...)` density denominator
    - Substitute a saturating magnitude function: `score = raw / (raw + K)`
    - Add `LEXICAL_SATURATION_K` to `config.py` (proposed default 12.0) and to
      `.env.example`; `K` shifts where thresholds sit and cannot change ranking
    - Preserve the existing `LexicalResult` shape and the 0.0-1.0 output range so
      `pre_classifier.py` and the property tests keep their contract
  - [x] 1.2 Add a stoplist to `LexicalEngine._tokenize()`
    - Seed from the existing `STOPWORDS` in `keyword_search.py`
    - Extend with interrogatives (`what`, `how`, `does`, `which`, `why`) and
      generic doc/meta verbs (`explain`, `summarize`, `describe`, `draft`,
      `review`, `general`, `typically`, `detailed`, `doc`), which Finding 3 shows
      carry max IDF in this corpus
    - Apply to indexing and scoring identically to keep IDF consistent
    - Consider extracting the list to a module-level constant or a data file so
      it can be tuned without touching scoring logic
  - [x] 1.3 Re-run the existing property tests in `tests/test_lexical_engine.py`
    - Property 2 (score bounds 0.0-1.0) must still hold; `raw/(raw+K)` is bounded
      by construction
    - Property 3 (verdict threshold consistency) must still hold
    - Property 1 (IDF correctness with dampening) is unaffected by 1.1 but the
      stoplist changes which tokens are indexed; update fixtures if they assert
      on specific tokens
  - _Addresses: Findings 1, 2, 3, 4. Fixes cases #9, #14._

- [x] 2. Remove the hardcoded-BLOCK fast path in `pre_classifier.py`
  - Worth doing on its own merits, independent of Task 1: this is the safety net
    that would have contained a scoring defect instead of amplifying it into an
    unreviewable BLOCK.
  - [x] 2.1 Stop asserting high-confidence enterprise ECI on `ENTERPRISE_LIKELY`
    - The `ENTERPRISE_LIKELY` branch currently returns `needs_llm=False` with
      `_build_enterprise_eci()` hardcoding `confidence=0.9`,
      `containsInternalArchitecture=True`, `containsImplementationDetails=True`
    - Route `ENTERPRISE_LIKELY` to the LLM (`needs_llm=True`), as `AMBIGUOUS`
      already does
    - Optionally retain a no-LLM path only for scores well clear of threshold,
      gated behind a new `TFIDF_HARD_ENTERPRISE_THRESHOLD` well above
      `TFIDF_ENTERPRISE_THRESHOLD`; a deterministic BLOCK should require
      overwhelming evidence, not a threshold crossing
    - Note the latency and token-cost tradeoff: more prompts reach the LLM. The
      `hard_block` (secrets) and `trivial` fast paths are untouched, so the
      highest-volume skips are preserved
  - [x] 2.2 Confirm `tests/test_pre_classifier_routing.py` Property 6 expectations
    - Property 6 currently asserts `ENTERPRISE_LIKELY -> enterprise_detected`
    - That assertion encodes the behavior being removed and must be updated
      deliberately, with the reasoning recorded
  - _Addresses: Finding 1. Prevents any future scoring drift from hard-blocking
    without review._

- [x] 3. Install the missing semantic dependencies
  - [x] 3.1 Install into the interpreter that actually serves the backend
    - `pip install sentence-transformers==3.4.1 faiss-cpu==1.14.3` (versions
      already pinned in `requirements.txt`)
    - This pulls `torch`, roughly 2 GB. Confirm before running.
  - [x] 3.2 Repair `backend/venv`
    - Currently missing `pyvenv.cfg`; `start-backend.ps1` targets it but the
      backend runs on system Python 3.14
    - Recreate the venv and install `requirements.txt` into it so the launcher
      and the runtime agree
  - [x] 3.3 Verify the semantic tier activates
    - `SemanticEngine unavailable` must disappear from startup logs
    - Confirm decision paths `semantic_confirmed_public` and
      `semantic_confirmed_enterprise` become reachable
    - Verify the FAISS index at `backend/ai/index/` builds or loads correctly
  - _Addresses: Finding 5. Restores the designed second opinion; until then the
    lexical score is the sole gate on the deterministic path._

- [x] 4. Gate Send Sanitized on BLOCK
  - [x] 4.1 Fix `browser-extension/interstitial/review.js`
    - Change `btnSendSanitized.hidden = !hasSanitizedChanges` to also hide on
      `status === "BLOCK"`
  - [x] 4.2 Apply the equivalent gate in `browser-extension/content/modal.js`
    - The in-page review dialog renders the same three actions and needs the
      same rule so both surfaces behave identically
  - [x] 4.3 Verify against suite case #4
    - On BLOCK, neither Send Original nor Send Sanitized should be available
  - _Addresses: Finding 6. Closes a BLOCK bypass._

- [x] 5. Suppress product-name PERSON false positives in Presidio
  - [x] 5.1 Add a post-detection allowlist filter in `presidio_engine.py`
    - Filter PERSON results whose span matches a known product or system name
    - Apply after `analyzer.analyze()` and before `_resolve_overlaps()` so
      masking and the reported `issues` list stay consistent
    - `MIN_SCORE` cannot be used for this: `Token Vault` and the real name
      `Rajesh Kumar` both score exactly 0.85 (Finding 7)
  - [x] 5.2 Source the allowlist from the knowledge corpus
    - Extract product and system names from `knowledge/products/` and
      `knowledge/architecture/` rather than hardcoding, so the list tracks the
      corpus
    - Confirmed necessary for `Token Vault` only; `Orion Identity`,
      `Merchant Registry`, `Atlas Core`, and `Nexus Gateway` already produce
      zero detections, so keep the list tight and evidence-driven
  - [x] 5.3 Regression-check real-name detection
    - `Rajesh Kumar` and equivalent control cases must still be detected and
      masked
  - _Addresses: Finding 7. Cosmetic in effect, but the false positive is what
    made the case #4 bypass in Task 4 exploitable._

- [x] 6. Add few-shot examples to `system_prompt.md`
  - Sequence after Tasks 1 and 2. Cases #12 and #13 reach the LLM today, but
    their behavior is currently confounded by the scoring defects; re-measure
    before tuning.
  - [x] 6.1 Cover generic compliance-framework questions
    - Mirror the existing `Explain OAuth2.` vs `Explain our OAuth2
      implementation.` contrast
    - Add: "summarize why GDPR, PCI DSS, and ISO 27001 matter for a company
      processing digital payments" -> `requiresEnterpriseKnowledge: false`
    - Contrast with: "what is our GDPR compliance status" -> `true`
  - [x] 6.2 Cover generic organizational-process questions
    - Add: "which teams are typically involved in reviewing a third-party vendor
      before onboarding" -> `requiresEnterpriseKnowledge: false`
    - Contrast with a prompt naming an internal process owner or system
  - [x] 6.3 Re-run cases #12 and #13 end-to-end
    - Both should land SAFE, or at most SANITIZE per the suite's
      "ALLOW / WARN" tolerance
  - _Addresses: cases #12 and #13._

- [x] 7. Surface ECI reasons in the issues panel
  - [x] 7.1 Include ECI-derived findings in the scan response
    - When a decision is driven by ECI flags with `entityCount == 0`, the client
      currently receives `issues: []`
    - Either extend `issues` in `routes.py` or have the client render matched
      rules and ECI flags when `issues` is empty
  - [x] 7.2 Verify against suite case #8
    - A correct BLOCK with zero entities must explain itself rather than showing
      "No specific issue details were returned by the scanner."
  - _Addresses: Finding 8._

- [x] 8. Expand the labelled suite and calibrate thresholds
  - The Task 1 result (AUC 1.000) rests on 3 BLOCK and 7 ALLOW cases with a
    ~1.4% margin. It establishes direction, not production-safe thresholds.
  - [x] 8.1 Grow `PromptShield_TestSuite.xlsx` to a meaningful sample
    - Target at least 30-50 labelled cases per class
    - Deliberately include near-miss pairs: generic vs possessive phrasings of
      the same topic, and short vs long phrasings of the same question
  - [x] 8.2 Calibrate `TFIDF_*` thresholds and `LEXICAL_SATURATION_K`
    - Choose thresholds from the measured score distribution, not by intuition
    - Record the resulting AUC and separation gap so future changes are
      comparable
  - [x] 8.3 Add a regression harness that reports AUC and separation gap
    - Make the metric from Finding 1 a standing check, so a future change that
      re-inverts the signal fails visibly instead of silently

## Validation

Each task states its own check. Suite-level acceptance:

- Cases #1, #2, #3, #6, #7 (secrets) continue to BLOCK via `hard_block`. These
  currently pass and must not regress.
- Cases #4, #5, #8 continue to BLOCK.
- Cases #9 through #15 return SAFE, or SANITIZE where the suite records
  "ALLOW / WARN".
- Separation gap on the lexical score is positive, and AUC is materially above
  0.5.
- Existing property tests in `tests/` pass, with any intentional expectation
  changes recorded in Tasks 1.3 and 2.2.

Do not treat a clean exit code as verification. The suite reports expected
verdicts per case; compare against those.

## Sequencing

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "2.1", "4.1", "4.2"] },
    { "id": 1, "tasks": ["1.3", "2.2", "4.3", "5.1", "5.2"] },
    { "id": 2, "tasks": ["5.3", "7.1", "3.1", "3.2"] },
    { "id": 3, "tasks": ["3.3", "7.2", "6.1", "6.2"] },
    { "id": 4, "tasks": ["6.3", "8.1"] },
    { "id": 5, "tasks": ["8.2", "8.3"] }
  ]
}
```

Rationale:

- Tasks 1, 2, and 4 carry the real weight and are independent of each other.
- Task 1 is atomic. Splitting 1.1 from 1.2 across releases regresses the suite.
- Task 3 is environmental and needs explicit approval for the ~2 GB torch
  download.
- Task 6 depends on Tasks 1 and 2 landing first, since its target cases are
  currently confounded.
- Task 8 is the durable fix for the calibration weakness the other tasks expose.

## Notes

- Findings were produced by temporary diagnostic scripts run against the real
  modules and corpus. Those scripts were removed after measurement; the numbers
  above are reproducible from the described method.
- Task 8.3 exists so this class of defect cannot recur silently. The current
  property tests verify internal consistency (score bounds, threshold logic) but
  nothing asserts that the score correlates with the intended outcome, which is
  why an AUC of 0.238 passed a green test suite.
