# backend/ai/ - Pre-Classification + Enterprise Context Intelligence (ECI)

This folder has two jobs, in order:

1. **Decide whether an LLM call is needed at all** (`pre_classifier.py`,
   `lexical_engine.py`, `semantic_engine.py`) - a three-tier lexical +
   semantic gate that resolves most prompts deterministically.
2. **When it genuinely is needed**, classify what the prompt *is* - intent,
   enterprise-context risk, compliance-framework impact - purely as a signal
   (the rest of this file, "ECI"). ECI never decides Allow/Warn/Mask/Block;
   that's `backend/policy/policy_engine.py`'s job, using this layer's output
   as one of its inputs.

## Pre-Classifier: the gate in front of the LLM

`pre_classifier.py`'s `pre_classify(prompt, masked_text, presidio_result)` is
called from `routes.py` immediately after Presidio, before ECI. It returns
`needs_llm: bool` plus a `decision_path` for logging/debugging. Priority
order (first match wins):

1. **Trivial** - small-talk prompt (`utils/helpers.py`'s `is_trivial_prompt()`)
   with zero Presidio entities → skip (`decision_path="trivial"`)
2. **Secrets** - any of `GITHUB_TOKEN`, `OPENAI_API_KEY`, `AWS_ACCESS_KEY`,
   `AWS_SECRET_KEY`, `PRIVATE_KEY`, `JWT_TOKEN` detected → skip, straight to
   a hard-block signal (`decision_path="hard_block"`) - always wins
   regardless of anything else
3. **Legacy mode** - if `PROMPTSHIELD_USE_LEGACY_SEARCH=true`, everything
   below is bypassed in favor of the old `keyword_search.py` overlap scoring
   (`_legacy_classify`), kept for rollback
4. **Lexical tier** (`lexical_engine.py`) - a TF-IDF inverted index built
   from `knowledge/` at startup scores the prompt in under 1ms:
   - `PUBLIC` (score below `PROMPTSHIELD_TFIDF_PUBLIC_THRESHOLD`, default
     0.15) → skip (`pii_only` if PII was found, else `general_knowledge`)
   - `ENTERPRISE_LIKELY` (score at/above `PROMPTSHIELD_TFIDF_ENTERPRISE_THRESHOLD`,
     default 0.45) → **call the LLM** (`enterprise_lexical_needs_review`). This
     used to skip the LLM and synthesize an ECI asserting
     `containsInternalArchitecture` at `confidence: 0.9`, which `rules.json`
     turns into an unreviewable BLOCK. A TF-IDF score is a retrieval signal
     (the corpus documents OAuth 2.0 and GDPR, so generic questions about them
     score highly too), not a disclosure judgement - so a high score now earns
     the prompt an LLM review rather than deciding its outcome. See
     [`../../specs/lexical-semantic-fix/plan.md`](../../specs/lexical-semantic-fix/plan.md)
     Finding 1.
   - `AMBIGUOUS` (between the two thresholds) → escalate to the semantic tier
5. **Semantic tier** (`semantic_engine.py`, only for `AMBIGUOUS` prompts) -
   embeds the prompt with a local `sentence-transformers` model
   (`PROMPTSHIELD_EMBEDDING_MODEL`, default `all-MiniLM-L6-v2`) and searches
   a FAISS `IndexFlatIP` built from chunked `knowledge/` docs (~50ms), then
   computes `hybrid = PROMPTSHIELD_HYBRID_LEXICAL_WEIGHT * tfidf +
   PROMPTSHIELD_HYBRID_SEMANTIC_WEIGHT * semantic`:
   - below `PROMPTSHIELD_HYBRID_PUBLIC_THRESHOLD` (default 0.30) → skip
     (`semantic_confirmed_public`)
   - at/above `PROMPTSHIELD_HYBRID_ENTERPRISE_THRESHOLD` (default 0.55) →
     skip (`semantic_confirmed_enterprise`)
   - otherwise → **call the LLM** (`true_ambiguity`)

When a tier skips the LLM, `pre_classifier.py` builds a `pre_eci` dict
(schema-shaped, matching `schema.json`) so `routes.py` and the Policy Engine
never need to special-case "no ECI ran" - they always get an ECI-shaped
result, either real (from the LLM) or synthesized here.

The FAISS index and chunk metadata persist to `ai/index/` (git-ignored) and
are only rebuilt when a `knowledge/` file's modification time changes -
otherwise startup loads them from disk. `keyword_search.py` is deliberately
kept, unused by default, purely as the `PROMPTSHIELD_USE_LEGACY_SEARCH`
fallback. Both `lexical_engine.py` and `semantic_engine.py` are imported
with graceful-failure handling in `pre_classifier.py`; if either fails to
load, prompts that would have used that tier fall through toward the LLM
rather than crashing.

Full design/requirements/property-test spec:
[`../../specs/lexical-semantic-upgrade/`](../../specs/lexical-semantic-upgrade/).

## ECI: when the LLM actually gets called

Prompts on the `true_ambiguity`, `enterprise_lexical_needs_review`, and
`engine_degraded` paths reach this section. Runs against a
local Ollama model (`phi3:mini` by default - see `backend/config.py`) or a
cloud provider via the Smart LLM Router (see `backend/README.md`), never the
raw prompt (only the already-masked text from `presidio/`, plus - when
available - the specific semantic chunks the pre-classifier's semantic tier
already retrieved, rather than full documents).

## Pipeline

```
masked_text (+ optional semantic_chunks from the pre-classifier's semantic tier)
    -> keyword_search.search()        top-k relevant knowledge/ snippets (still runs
                                       unconditionally, alongside any semantic_chunks)
    -> prompt_builder.build_prompt()  {system, user} messages, schema.json
                                       rendered into the system prompt; prefers
                                       semantic_chunks when provided, falls back
                                       to the full retrieved_docs otherwise
    -> llm_router.call()              routes to Ollama/Groq/Gemini/Bedrock per
                                       PROMPTSHIELD_LLM_STRATEGY, format:"json", temp=0
    -> jsonschema.validate()          against schema.json
    -> ECIClassificationResult dict
```

`semantic_classifier.classify(masked_text, entity_count=0, semantic_chunks=None)`
is the only function callers need. It **never raises** - every failure path
(no LLM provider reachable, output that doesn't parse or validate even after
one retry) returns a schema-shaped fail-closed dict instead, so `routes.py`
never needs its own try/except around this call.

## Files

- **`pre_classifier.py`** - the three-tier gate described above; owns
  `pre_classify()` and the priority routing between trivial/secrets/lexical/
  semantic tiers.
- **`lexical_engine.py`** - `LexicalEngine` builds the in-memory TF-IDF
  inverted index from `context_loader`'s documents at startup and exposes
  `score(prompt) -> LexicalResult` (tfidf_score, verdict, top_docs,
  matched_terms). Terms appearing in over 60% of docs get near-zero IDF
  weight so generic vocabulary can't inflate scores.
- **`semantic_engine.py`** - `SemanticEngine` loads a local
  `sentence-transformers` model, chunks `knowledge/` docs (on `##` headings
  or ~500-char paragraphs), builds/persists a FAISS `IndexFlatIP` under
  `ai/index/`, and exposes `search(prompt, top_k) -> SemanticResult`.
- **`context_loader.py`** - walks `knowledge/*.md` into memory (in-process
  cache, `force_reload=True` to bust it). `knowledge_index.json` exists as a
  stub for a future indexed lookup but isn't used yet - this walks the
  filesystem directly.
- **`keyword_search.py`** - token-overlap scoring over loaded docs (legacy
  MVP approach, no vector DB/embeddings). Superseded by `lexical_engine.py`/
  `semantic_engine.py` for pre-classification routing, but still called
  unconditionally inside `semantic_classifier.classify()` for `retrieved_docs`,
  and used as the sole scorer when `PROMPTSHIELD_USE_LEGACY_SEARCH=true`.
  Returns `[]` when nothing scores above `min_score`; that's a normal, common
  result, not an error.
- **`prompt_builder.py`** - assembles the final `{system, user}` prompt.
  `_generate_schema_instructions()` renders `schema.json`'s `required` fields
  into the output-format block **automatically** - adding/removing a schema
  field never requires touching `prompts/system_prompt.md` by hand for the
  format block itself (the *cues/examples* teaching the model how to use a
  new field still go in `system_prompt.md`, see below).
- **`ollama_client.py`** - thin HTTP client for Ollama's `/api/chat`.
  `temperature: 0` + `top_p: 0.1` for reproducible classification;
  `format: "json"` plus the schema block are two independent layers of
  defense against prose wrapping the JSON. Retries once on network/timeout
  errors with linear backoff. `is_ollama_available()` / `warm_up()` support
  graceful-degradation callers.
- **`semantic_classifier.py`** - orchestrates the pipeline above and owns the
  two non-LLM default results callers use:
  - **`_fallback_result(reason)`** - fail-**closed**. Used when Ollama is
    down or output can't be trusted. `confidence: 0.0` is what actually
    drives caution (`rules.json`'s `warn_eci_could_not_classify` keys off
    this) - no boolean field ever speculates `True` here; booleans can't
    express "unknown," so that concept lives entirely in `confidence`.
  - **`skipped_result(reason)`** - fail-**open**, deliberately the opposite
    posture. Used by the Smart Analysis Router (see below) when a prompt was
    never sent to Ollama at all because it's trivial. `confidence: 1.0` +
    all flags `False` - reusing `_fallback_result()` here would incorrectly
    WARN on every skipped "hi".
- **`schema.json`** - the single source of truth for the ECI output contract
  (`additionalProperties: false`, all 14 fields required). Includes content
  classification (`intent`, `documentType`, `containsX` flags) and compliance
  mapping (`impactsGDPR`, `impactsPCIDSS`, `impactsHIPAA`, `impactsISO27001`).
  `impactsGDPR` also covers EULA/consent/terms-of-service content, since
  that's how GDPR-relevant consent and data-processing terms actually get
  written down - not a separate field.
- **`prompts/system_prompt.md`** / **`prompts/classifier_prompt.md`** -
  system role/rules and per-request template, respectively.

## Tier 0 detail: the trivial-prompt check

`backend/utils/helpers.py`'s `is_trivial_prompt()` (not part of this folder,
but this folder's - specifically `pre_classifier.py`'s - dependency) is the
very first check in the pre-classifier gate described above. This is
deliberately **not agentic** - its whole job is avoiding unnecessary LLM
calls, so spending an LLM call to decide whether to make an LLM call would
defeat the purpose. It's a bag-of-words small-talk check, not a length
cutoff: word count alone can't tell "Hi, how are you?" (trivial) apart from
"Explain our Mercury architecture" (not trivial, same length) - see the
function's docstring for the full reasoning, and `tests/test_scenarios.md`'s
A9 section for the boundary cases this protects against regressing.

`pre_classifier.py` only treats a prompt as trivial when Presidio *also*
found zero entities - a prompt Presidio flags always proceeds to the
lexical/semantic tiers regardless of length.

## Known limitation - compliance schema size vs. model reliability

Confirmed via live smoke test, not hypothetical: growing `schema.json` from
10 to 14 required fields (adding the 4 `impactsX` compliance flags)
measurably increased how often `phi3:mini` produces a malformed response - a
corrupted field name or a missing required field - triggering the fail-closed
`_fallback_result()` path more than before. A live A/B at
`ollama_client.py`'s `num_predict` 300 vs. 450 produced **byte-identical**
completions, confirming this is a genuine small-model generation limitation
at this schema size, not a token-budget/truncation issue. It's safe (every
failure still resolves to a cautious WARN, never a silent pass-through) but
real - see `tests/test_scenarios.md`'s B5 section for reproduction cases and
options worth a team decision (larger/instruction-tuned model, or splitting
compliance mapping into its own lighter schema/call).

## Running standalone

```
python backend/ai/context_loader.py       # confirm knowledge/ docs load
python backend/ai/keyword_search.py       # confirm legacy retrieval scoring
python backend/ai/ollama_client.py        # single raw Ollama call
python backend/ai/semantic_classifier.py  # full pipeline, hardcoded prompts
python tests/test_eci_smoke.py            # from repo root - fuller case list,
                                           # "expected direction" not exact
                                           # match (LLM output isn't fully
                                           # deterministic across model/
                                           # hardware changes even at temp=0)
```

The last four require Ollama running locally with the configured model
pulled (`ollama pull phi3:mini`, or override via `PROMPTSHIELD_OLLAMA_MODEL`)
- or a configured cloud provider (see `backend/README.md`'s Smart LLM
Router). The pre-classifier tiers do **not** require Ollama - run their
tests directly instead:

```
pytest tests/test_lexical_engine.py            # Property 1: IDF correctness
pytest tests/test_semantic_engine.py           # Property 5: semantic score bounds/ordering
pytest tests/test_pre_classifier_routing.py    # Property 6: priority routing
pytest tests/test_hybrid_scoring.py            # Property 7: hybrid formula
pytest tests/test_prompt_builder.py            # Property 9: context inclusion
pytest tests/test_integration_routing.py       # end-to-end routing, mocked externals
```
