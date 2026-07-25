# Implementation Plan: Lexical + Semantic Retrieval Upgrade

## Overview

Replace the naive keyword-overlap scoring in `keyword_search.py` with a production-grade two-layer retrieval system. Implementation proceeds in layers: configuration first, then the lexical engine (fast, deterministic), then the semantic engine (embeddings + FAISS), then wiring them into the pre-classifier and prompt builder, and finally integration testing.

## Tasks

- [x] 1. Add configuration variables and dependencies
  - [x] 1.1 Add new environment variables to `backend/config.py`
    - Add TF-IDF thresholds (TFIDF_PUBLIC_THRESHOLD, TFIDF_ENTERPRISE_THRESHOLD)
    - Add semantic engine settings (EMBEDDING_MODEL, SEMANTIC_CHUNK_SIZE)
    - Add hybrid scoring settings (HYBRID_LEXICAL_WEIGHT, HYBRID_SEMANTIC_WEIGHT, HYBRID_PUBLIC_THRESHOLD, HYBRID_ENTERPRISE_THRESHOLD)
    - Add legacy fallback toggle (USE_LEGACY_SEARCH)
    - Follow existing dotenv pattern with `os.environ.get()` and sensible defaults
    - _Requirements: 8.1, 8.2_

  - [x] 1.2 Update `backend/.env.example` with new variable placeholders
    - Add all PROMPTSHIELD_TFIDF_*, PROMPTSHIELD_EMBEDDING_*, PROMPTSHIELD_SEMANTIC_*, PROMPTSHIELD_HYBRID_*, PROMPTSHIELD_USE_LEGACY_SEARCH entries with default values as comments
    - _Requirements: 8.1_

  - [x] 1.3 Add `sentence-transformers` and `faiss-cpu` to `backend/requirements.txt`
    - Add pinned versions for sentence-transformers and faiss-cpu
    - Add hypothesis as a dev/test dependency
    - _Requirements: 11.1_

- [x] 2. Implement the Lexical Engine
  - [x] 2.1 Create `backend/ai/lexical_engine.py` with `LexicalEngine` class
    - Implement `LexicalConfig` and `LexicalResult` dataclasses
    - Implement `__init__` that builds inverted index from context_loader documents
    - Implement `_tokenize` method (regex `[a-zA-Z][a-zA-Z0-9_-]+`, lowercase, filter len > 2)
    - Implement `_build_index` method (token → list[(doc_id, tf)] + df count, IDF cache)
    - Implement `score` method (TF-IDF scoring, normalization to 0.0–1.0, verdict classification)
    - Apply high-frequency dampening: tokens in >60% docs get near-zero IDF
    - Guard against division by zero with max(df, 1)
    - Return empty/PUBLIC result for empty prompts or empty knowledge base
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 2.2 Write property test for IDF correctness (Property 1)
    - **Property 1: IDF Correctness with High-Frequency Dampening**
    - Use Hypothesis to generate random corpora (1-100 docs) and random token distributions
    - Verify IDF = log(N/df(t)) when df/N <= 0.60 and IDF < 0.01 when df/N > 0.60
    - Create `tests/test_lexical_engine.py`
    - **Validates: Requirements 1.2, 1.3**

  - [x] 2.3 Write property test for TF-IDF score bounds (Property 2)
    - **Property 2: TF-IDF Score Bounds Invariant**
    - Use Hypothesis to generate random prompt strings and random document sets
    - Verify returned score is always in [0.0, 1.0] inclusive
    - **Validates: Requirements 2.1**

  - [x] 2.4 Write property test for verdict threshold consistency (Property 3)
    - **Property 3: Lexical Verdict Threshold Consistency**
    - Use Hypothesis to generate random scores and threshold pairs
    - Verify verdict is exactly PUBLIC/AMBIGUOUS/ENTERPRISE_LIKELY based on threshold boundaries
    - Verify the three cases are mutually exclusive and exhaustive
    - **Validates: Requirements 2.2, 2.3, 2.4**

- [x] 3. Checkpoint - Lexical engine complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement the Semantic Engine
  - [x] 4.1 Create `backend/ai/semantic_engine.py` with `SemanticEngine` class
    - Implement `SemanticConfig` and `SemanticResult` dataclasses
    - Implement `__init__` that loads or builds FAISS index
    - Implement `_chunk_documents` (split on `##` headings, then by ~500 char paragraphs)
    - Implement `_build_index` (embed chunks with sentence-transformers, build FAISS IndexFlatIP)
    - Implement `_load_persisted_index` (check mtimes.json, load faiss.index + chunks.json)
    - Implement `_persist_index` (save to `backend/ai/index/` directory)
    - Implement `search` method (embed prompt, FAISS inner-product search, return top-k)
    - Handle graceful degradation: model download failure, empty index, embedding errors
    - Normalize embeddings for inner-product similarity (cosine via normalized vectors)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.1, 4.2, 4.3_

  - [x] 4.2 Create `backend/ai/index/` directory with `.gitkeep`
    - Create the index persistence directory
    - Add `.gitignore` in `backend/ai/index/` to exclude `faiss.index`, `chunks.json`, `mtimes.json` from version control
    - _Requirements: 3.5_

  - [x] 4.3 Write property test for document chunking bounds (Property 4)
    - **Property 4: Document Chunking Size Bounds**
    - Use Hypothesis to generate random Markdown documents with headings
    - Verify every chunk has length <= 2 * chunk_size
    - Verify concatenation of chunks preserves all non-whitespace content
    - Create `tests/test_semantic_engine.py`
    - **Validates: Requirements 3.4**

  - [x] 4.4 Write property test for semantic score bounds and ordering (Property 5)
    - **Property 5: Semantic Search Score Bounds and Ordering**
    - Use Hypothesis with a test FAISS index (small fixture)
    - Verify semantic score is in [0.0, 1.0]
    - Verify returned top-k chunks are sorted by descending similarity
    - **Validates: Requirements 4.1, 4.2**

- [x] 5. Checkpoint - Semantic engine complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Update Pre-Classifier with hybrid routing
  - [x] 6.1 Update `backend/ai/pre_classifier.py` with three-tier routing logic
    - Import LexicalEngine and SemanticEngine (with graceful import failure handling)
    - Add legacy fallback: if USE_LEGACY_SEARCH is true, use existing keyword_search
    - Replace PATH 4 (general_knowledge) with lexical verdict-based routing
    - Add new decision paths: `enterprise_detected`, `semantic_confirmed_public`, `semantic_confirmed_enterprise`, `true_ambiguity`
    - For AMBIGUOUS verdict: invoke SemanticEngine, compute hybrid score (0.4*lex + 0.6*sem)
    - Apply hybrid thresholds to determine final routing
    - Add `lexical_result`, `semantic_result`, `hybrid_score` to return dict
    - Handle degradation: if lexical engine unavailable, fall through to LLM; if semantic unavailable, treat AMBIGUOUS as → LLM
    - Preserve existing PATH 1 (trivial), PATH 2 (hard_block), and PII detection logic
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 6.3, 6.4, 9.1, 9.2, 9.3, 9.4_

  - [x] 6.2 Write property test for pre-classifier priority routing (Property 6)
    - **Property 6: Pre-Classifier Priority Routing**
    - Use Hypothesis to generate random combinations of (secrets, PII, lexical_verdict)
    - Verify secrets always produce hard_block regardless of other signals
    - Verify PII + PUBLIC → pii_only
    - Verify PUBLIC + no PII → general_knowledge
    - Verify ENTERPRISE_LIKELY → enterprise_detected
    - Verify AMBIGUOUS → semantic engine invoked
    - Create `tests/test_pre_classifier_routing.py`
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

  - [x] 6.3 Write property test for hybrid score formula (Property 7)
    - **Property 7: Hybrid Score Formula Correctness**
    - Use Hypothesis to generate random float pairs in [0.0, 1.0]
    - Verify hybrid_score = 0.4 * tfidf_score + 0.6 * semantic_score (with configurable weights)
    - Create `tests/test_hybrid_scoring.py`
    - **Validates: Requirements 6.1**

  - [x] 6.4 Write property test for hybrid routing thresholds (Property 8)
    - **Property 8: Hybrid Routing Threshold Consistency**
    - Use Hypothesis to generate random hybrid scores in [0.0, 1.0]
    - Verify routing decision matches threshold boundaries exactly
    - Verify three cases are mutually exclusive and exhaustive
    - **Validates: Requirements 6.2, 6.3, 6.4**

- [x] 7. Update Prompt Builder with semantic chunks
  - [x] 7.1 Update `backend/ai/prompt_builder.py` to accept and format semantic chunks
    - Add optional `semantic_chunks: list[dict] | None` parameter to `build_prompt`
    - When semantic_chunks provided: format as targeted context sections (~500 chars each)
    - When no semantic_chunks: fall back to existing full-document formatting
    - Preserve existing prompt structure (system prompt with schema, user prompt with knowledge + masked text)
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 7.2 Write property test for prompt builder context inclusion (Property 9)
    - **Property 9: Prompt Builder Context Inclusion**
    - Use Hypothesis to generate random chunk lists and document lists
    - Verify chunks appear in output when provided
    - Verify fallback to full documents when no chunks
    - Verify output always has "system" and "user" keys with non-empty strings
    - Create `tests/test_prompt_builder.py`
    - **Validates: Requirements 7.1, 7.2, 7.3**

- [x] 8. Checkpoint - All components wired together
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Integration wiring and final touches
  - [x] 9.1 Create `tests/conftest.py` with shared fixtures
    - Create test corpus generators for Hypothesis strategies
    - Create fixture for small FAISS index (pre-built, fast to load)
    - Create mock presidio results for routing tests
    - Add shared configuration fixtures
    - _Requirements: 10.1, 10.2, 10.3_

  - [x] 9.2 Verify routes.py integration and update if needed
    - Check that `routes.py` passes semantic results from pre_classifier to prompt_builder
    - Pass `semantic_chunks` from pre_classifier's semantic_result to `build_prompt` when LLM path is taken
    - Ensure backward compatibility of API response schema
    - _Requirements: 5.5, 7.1_

  - [x] 9.3 Write integration tests for end-to-end routing decisions
    - Create `tests/test_routing_decisions.py` with labeled prompt suite
    - Test: trivial prompt → general_knowledge path
    - Test: enterprise keyword prompt → enterprise_detected path
    - Test: ambiguous prompt → semantic path → hybrid threshold routing
    - Test: legacy fallback toggle produces backward-compatible results
    - Verify FAISS index persistence: build → "restart" → verify loaded from disk
    - _Requirements: 9.1, 9.2, 9.3, 10.1, 10.2, 10.3_

- [x] 10. Final checkpoint - Feature complete
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties defined in the design document
- Unit tests validate specific examples and edge cases
- The implementation language is Python, matching the existing codebase
- The `keyword_search.py` module is preserved (not deleted) to support the legacy fallback path
- The `backend/ai/index/` directory should be gitignored to avoid committing large binary FAISS indexes

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["2.1", "4.2"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "4.1"] },
    { "id": 3, "tasks": ["4.3", "4.4"] },
    { "id": 4, "tasks": ["6.1", "7.1"] },
    { "id": 5, "tasks": ["6.2", "6.3", "6.4", "7.2", "9.1"] },
    { "id": 6, "tasks": ["9.2"] },
    { "id": 7, "tasks": ["9.3"] }
  ]
}
```
