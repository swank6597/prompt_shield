# Enterprise Context Intelligence (ECI)

The one layer in PromptShield that calls an LLM. It classifies what a prompt
*is* - intent, enterprise-context risk, compliance-framework impact - purely
as a signal. It never decides Allow/Warn/Mask/Block; that's
`backend/policy/policy_engine.py`'s job, using this layer's output as one of
its inputs. Runs against a local Ollama model (`phi3:mini` by default - see
`backend/config.py`), never the raw prompt (only the already-masked text from
`presidio/`).

## Pipeline

```
masked_text
    -> keyword_search.search()        top-k relevant knowledge/ snippets
    -> prompt_builder.build_prompt()  {system, user} messages, schema.json
                                       rendered into the system prompt
    -> ollama_client.call_ollama()    POST /api/chat, format:"json", temp=0
    -> jsonschema.validate()          against schema.json
    -> ECIClassificationResult dict
```

`semantic_classifier.classify(masked_text)` is the only function callers
need. It **never raises** - every failure path (Ollama unreachable, output
that doesn't parse or validate even after one retry) returns a schema-shaped
fail-closed dict instead, so `routes.py` never needs its own try/except
around this call.

## Files

- **`context_loader.py`** - walks `knowledge/*.md` into memory (in-process
  cache, `force_reload=True` to bust it). `knowledge_index.json` exists as a
  stub for a future indexed lookup but isn't used yet - this walks the
  filesystem directly.
- **`keyword_search.py`** - token-overlap scoring over loaded docs (MVP, no
  vector DB/embeddings - explicitly deferred future work). Returns `[]` when
  nothing scores above `min_score`; that's a normal, common result, not an
  error.
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

## Smart Analysis Router (not part of this folder, but this folder's caller)

`backend/utils/helpers.py`'s `is_trivial_prompt()` decides, in `routes.py`,
whether to call `classify()` at all. This is deliberately **not agentic** -
its whole job is avoiding unnecessary Ollama calls, so spending an LLM call to
decide whether to make an LLM call would defeat the purpose and add 30-180s
of latency for zero benefit on constrained hardware. It's a bag-of-words
small-talk check, not a length cutoff: word count alone can't tell "Hi, how
are you?" (trivial) apart from "Explain our Mercury architecture" (not
trivial, same length) - see the function's docstring for the full reasoning,
and `tests/test_scenarios.md`'s A9 section for the boundary cases this
protects against regressing.

`routes.py` only skips ECI when Presidio *also* found zero entities - a
prompt Presidio flags always gets the full ECI pass regardless of length.

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
python backend/ai/keyword_search.py       # confirm retrieval scoring
python backend/ai/ollama_client.py        # single raw Ollama call
python backend/ai/semantic_classifier.py  # full pipeline, hardcoded prompts
python tests/test_eci_smoke.py            # from repo root - fuller case list,
                                           # "expected direction" not exact
                                           # match (LLM output isn't fully
                                           # deterministic across model/
                                           # hardware changes even at temp=0)
```

All require Ollama running locally with the configured model pulled
(`ollama pull phi3:mini`, or override via `PROMPTSHIELD_OLLAMA_MODEL`).
