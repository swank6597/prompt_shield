# Spec: Lexical + Semantic Retrieval Upgrade

**Status: implemented.** This spec drove the TF-IDF lexical engine + FAISS semantic
engine + three-tier pre-classifier now running in `backend/ai/` (`lexical_engine.py`,
`semantic_engine.py`, `pre_classifier.py`). For the shipped behavior, see
[`../../backend/ai/README.md`](../../backend/ai/README.md) and
[`../../backend/README.md`](../../backend/README.md#lexical--semantic-pre-classification) —
those describe the system as it actually runs today; the documents in this folder are
the design record of how it got built.

## Documents (Kiro spec-driven workflow, requirements → design → tasks)

- **[`requirements.md`](requirements.md)** — the authoritative requirement/acceptance-criteria
  list (EARS-style "WHEN/THE .. SHALL" statements), with a glossary of terms
  (Lexical_Engine, Semantic_Engine, Verdict, Hybrid_Score, etc.).
- **[`design.md`](design.md)** — the technical design: architecture diagrams, module
  interfaces, data models, 9 formally-stated correctness properties (each mapped to
  requirements and to a Hypothesis property test), error-handling/degradation strategy,
  and testing strategy.
- **[`tasks.md`](tasks.md)** — the implementation task breakdown with a dependency-wave
  graph; every task is checked off (`[x]`) as complete.
- **[`promptshield_merged_best_outcome_plan.md`](promptshield_merged_best_outcome_plan.md)** —
  an earlier brainstorm/planning document that preceded the formal spec (merging two
  independent proposals: cheap lexical gating + FAISS semantic search). Superseded by
  `requirements.md`/`design.md` for anything where they disagree; kept for context on
  *why* the two-layer approach was chosen.
- `.config.kiro` / `tasks.meta.json` — Kiro spec-tool bookkeeping (spec metadata,
  property-test execution history). Not meant to be hand-edited or read as documentation.

## If you're changing this system further

Update `requirements.md`/`design.md` first (or write a new spec folder) rather than
just editing code — the property-based tests in `tests/test_lexical_engine.py`,
`tests/test_semantic_engine.py`, `tests/test_pre_classifier_routing.py`,
`tests/test_hybrid_scoring.py`, and `tests/test_prompt_builder.py` are written directly
against the correctness properties in `design.md` and will need matching updates.
