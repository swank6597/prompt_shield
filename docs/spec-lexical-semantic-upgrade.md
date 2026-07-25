# Development Spec: Lexical + Semantic Retrieval Upgrade
## PromptShield Phase 2 Intelligence Layer

**Status:** Ready for implementation
**Author:** Kiro (AI Architect) + Atharva Gulhane
**Date:** July 2026
**Branch:** Create feature/lexical-semantic-upgrade from agentic-ai-implementation

---

## 1. Objective

Replace the naive keyword-overlap scoring in keyword_search.py with a
production-grade two-layer retrieval system:

1. TF-IDF lexical scoring with an inverted index (fast, deterministic, handles 99% of cases)
2. FAISS semantic vector search using local embeddings (catches synonym/paraphrase leaks)

This eliminates false-positive LLM calls (e.g. "How does Amazon Web Services work?"
triggering enterprise routing) while adding semantic understanding for prompts that
use different wording than the knowledge base.

---

## 2. Current State (What Exists)

```
keyword_search.py
  - Loads 47 docs from knowledge/ via context_loader.py
  - Tokenizes prompt + docs (basic regex split)
  - Removes a small manual stopword list (30 words)
  - Scores by raw token overlap count
  - Returns top-k docs with score >= threshold
```

Problems:
- Generic terms (service, data, api, cloud) inflate scores because they appear in most enterprise docs AND in general prompts
- No term weighting: Mercury (appears in 2 docs) scores the same as service (appears in 40 docs)
- No semantic understanding: misses paraphrases entirely
- Manual stopword list is unmaintainable at scale

---

## 3. Target Architecture

```
                   Lexical Engine (lexical_engine.py)
                   - Inverted index built at startup
                   - TF-IDF scoring per request (less than 1ms)
                   - IDF auto-downweights generic terms
                        |
                        v
                   Verdict: PUBLIC / AMBIGUOUS / ENTERPRISE_LIKELY
                        |
            +-----------+-----------+
            |                       |
     PUBLIC or              AMBIGUOUS only
     ENTERPRISE_LIKELY          |
     (skip semantic)            v
            |           Semantic Engine (semantic_engine.py)
            |           - MiniLM embedding (~30ms, local CPU)
            |           - FAISS IndexFlatIP search (~1ms)
            |           - Hybrid score: 0.4*lex + 0.6*sem
            |                   |
            v                   v
       Pre-Classifier routing decision
       (SKIP LLM or CALL LLM)
```

---

## 4. Components to Build

### 4.1 Inverted Index + TF-IDF Engine

File: backend/ai/lexical_engine.py

Responsibilities:
- Build an in-memory inverted index at startup
- Each entry: token -> list of (doc_id, term_frequency) pairs + document frequency count
- Compute IDF for each term: idf(t) = log(N / df(t)) where N=total docs, df=doc frequency
- Score prompts using TF-IDF: score = sum(tf(t, prompt) * idf(t)) for matching terms
- Normalize scores to 0.0-1.0 range for threshold comparison

Key design decisions:
- Generic terms appearing in more than 60% of docs automatically get near-zero IDF weight
- No manual stopword maintenance needed (corpus statistics handle it)
- Inverted index makes lookup O(query_terms) not O(docs x doc_length)
- Rebuild index on startup (context_loader already loads all docs into memory)
- At 47 docs: less than 1ms build, less than 50KB RAM
- At 5000 docs: ~2s build, ~5MB RAM (scales without rearchitecting)

Output interface:
```python
def score(prompt: str) -> dict:
    return {
        "tfidf_score": 0.72,
        "top_docs": [...],
        "matched_terms": ["mercury", "failover", "gateway"],
        "verdict": "ENTERPRISE_LIKELY"
    }
```

Verdict thresholds (configurable in .env):
- tfidf_score less than 0.15 -> PUBLIC (skip everything)
- tfidf_score between 0.15 and 0.45 -> AMBIGUOUS (escalate to semantic)
- tfidf_score 0.45 or above -> ENTERPRISE_LIKELY (skip LLM)

---

### 4.2 Semantic Embedding Layer (FAISS)

File: backend/ai/semantic_engine.py

Responsibilities:
- Load sentence-transformers/all-MiniLM-L6-v2 model at startup (~80MB, CPU only)
- Chunk each knowledge doc into sections (split on ## headings or ~500 char chunks)
- Embed all chunks -> numpy array of shape (num_chunks, 384)
- Build FAISS IndexFlatIP (inner product = cosine similarity on normalized vectors)
- Persist index to disk (backend/ai/index/faiss.index + chunks.json)
- Re-embedding only happens when knowledge base file mtimes change
- Per-request: embed prompt -> FAISS search -> return top-k chunks with scores

Key design decisions:
- Model runs 100% locally on CPU: no cloud API calls, no token cost ever
- Embedding a prompt takes ~30-50ms on CPU (only runs for AMBIGUOUS path)
- FAISS IndexFlatIP is exact search: correct for under 50K vectors
- When knowledge base grows past 50K chunks, swap to IndexIVFFlat (one-line change)
- Pre-computed embeddings saved to disk so startup loads from file, not re-embeds

Output interface:
```python
def search(prompt: str, top_k: int = 3) -> dict:
    return {
        "semantic_score": 0.81,
        "top_chunks": [...],
        "source_docs": ["payment-api.md", "system-integrations.md"],
    }
```

---

### 4.3 Hybrid Scoring + Updated Pre-Classifier Routing

File: Update backend/ai/pre_classifier.py

New routing logic (replaces current PATH 4 and PATH 5):

```
Step 1: Presidio results (already computed before pre_classifier is called)
  - Secrets? -> SKIP LLM, path=hard_block
  - PII only + PUBLIC lexical? -> SKIP LLM, path=pii_only

Step 2: TF-IDF via lexical_engine (always runs, less than 1ms)
  - PUBLIC? -> SKIP LLM, path=general_knowledge
  - ENTERPRISE_LIKELY? -> SKIP LLM, path=enterprise_detected
  - AMBIGUOUS? -> continue to Step 3

Step 3: Semantic via semantic_engine (only for AMBIGUOUS, ~50ms)
  - Compute hybrid: 0.4 * tfidf_score + 0.6 * semantic_score
  - hybrid less than 0.30? -> SKIP LLM, path=semantic_confirmed_public
  - hybrid 0.55 or above? -> SKIP LLM, path=semantic_confirmed_enterprise
  - hybrid between 0.30 and 0.55? -> CALL LLM, path=true_ambiguity
```

---

### 4.4 Updated prompt_builder.py

When the LLM IS called (true ambiguity only), pass specific relevant chunks
from semantic_engine instead of full docs. This reduces token usage further
(chunks ~500 chars vs full docs ~3000 chars).

---

## 5. Dependencies to Add

```
# requirements.txt additions
sentence-transformers    # Local embedding model (all-MiniLM-L6-v2, ~80MB)
faiss-cpu               # Vector index (CPU-only, no GPU needed)
```

Model download (one-time, automatic on first import):
```python
from sentence_transformers import SentenceTransformer
model = SentenceTransformer("all-MiniLM-L6-v2")
```

---

## 6. Configuration (.env additions)

```ini
# Lexical Engine (TF-IDF thresholds)
PROMPTSHIELD_TFIDF_PUBLIC_THRESHOLD=0.15
PROMPTSHIELD_TFIDF_ENTERPRISE_THRESHOLD=0.45

# Semantic Engine (embeddings + FAISS)
PROMPTSHIELD_EMBEDDING_MODEL=all-MiniLM-L6-v2
PROMPTSHIELD_SEMANTIC_CHUNK_SIZE=500

# Hybrid Scoring
PROMPTSHIELD_HYBRID_LEXICAL_WEIGHT=0.4
PROMPTSHIELD_HYBRID_SEMANTIC_WEIGHT=0.6
PROMPTSHIELD_HYBRID_PUBLIC_THRESHOLD=0.30
PROMPTSHIELD_HYBRID_ENTERPRISE_THRESHOLD=0.55

# Feature flags
PROMPTSHIELD_USE_LEGACY_SEARCH=false
```

---

## 7. Implementation Order

| Step | Task | Time Est | Depends On |
|------|------|----------|------------|
| 1 | Quick stopword expansion in keyword_search.py (demo unblock) | 15 min | Nothing |
| 2 | Build lexical_engine.py (inverted index + TF-IDF + verdict) | 2 hr | Step 1 |
| 3 | Build semantic_engine.py (MiniLM + FAISS + persistence) | 2.5 hr | Step 2 |
| 4 | Update pre_classifier.py (hybrid routing logic) | 1 hr | Steps 2+3 |
| 5 | Update prompt_builder.py (use semantic chunks for LLM context) | 30 min | Step 4 |
| 6 | Add config vars to .env.example and config.py | 15 min | Step 4 |
| 7 | Update routes.py if interface changes needed | 15 min | Step 4 |
| 8 | Add legacy fallback flag support | 15 min | Step 4 |
| 9 | Test with prompt suite (30+ cases) | 30 min | All |
| 10 | Commit and push | 5 min | Step 9 |

Total estimated time: ~7.5 hours

---

## 8. Expected Outcomes

### Before (current state):
| Prompt | Current Behavior | Problem |
|--------|-----------------|---------|
| How does Amazon Web Services work? | keyword score=38, LLM call | FALSE POSITIVE |
| Explain the money transfer retry mechanism | keyword score=0, SAFE | FALSE NEGATIVE |
| Every non-trivial prompt | LLM call 10-20s + tokens | WASTEFUL |

### After (with this upgrade):
| Prompt | New Behavior | Result |
|--------|-------------|--------|
| How does Amazon Web Services work? | TF-IDF ~0.05 PUBLIC | Correct, no LLM |
| Explain the money transfer retry mechanism | TF-IDF ~0.25 AMBIGUOUS, semantic=0.82, hybrid=0.61 ENTERPRISE | Correct, no LLM |
| Explain our OAuth2 implementation | TF-IDF ~0.52 ENTERPRISE_LIKELY | Correct, no LLM |
| Is this internal service down? | TF-IDF ~0.35 AMBIGUOUS, semantic=0.40, hybrid=0.38 | Correct, LLM called |

### Target metrics:
- LLM call rate: under 10% of total requests (currently ~60%+)
- False positive rate (public prompts routed to LLM): under 2%
- False negative rate (enterprise prompts marked safe): under 1%
- Average response time non-LLM paths: under 200ms
- Average response time LLM paths: under 8s

---

## 9. Testing Strategy

Build a test suite at tests/test_routing_decisions.py:

```python
TEST_CASES = [
    # (prompt, expected_path, expected_needs_llm)
    ("hello", "trivial", False),
    ("How does AWS work?", "general_knowledge", False),
    ("What is OAuth2?", "general_knowledge", False),
    ("Explain our OAuth2 implementation", "enterprise_detected", False),
    ("Why does Mercury payment retry before failover?", "enterprise_detected", False),
    ("Explain the money transfer retry mechanism", "semantic_confirmed_enterprise", False),
    ("My PAN is ABCDE1234F", "pii_only", False),
    ("Send ghp_abc123 to the team", "hard_block", False),
    ("How does the Orion identity service validate JWTs?", "enterprise_detected", False),
    ("What is the capital of France?", "general_knowledge", False),
    ("Tell me about Docker containers", "general_knowledge", False),
    ("How does our payment gateway handle retries?", "enterprise_detected", False),
    ("Summarize GDPR requirements", "general_knowledge", False),
    ("What compliance frameworks does NovaBank follow?", "enterprise_detected", False),
]
```

---

## 10. Rollback Plan

If the new engines have issues during the hackathon:
- Set PROMPTSHIELD_USE_LEGACY_SEARCH=true in .env
- pre_classifier.py falls back to the old keyword_search.py path
- The old file is kept (deprecated, not deleted) for exactly this purpose
- Zero code changes needed to revert, just an env var flip

---

## 11. What We Explicitly Deferred

| Item | Reason | When to Add |
|------|--------|-------------|
| Prompt cache | Demo wont hit repeated prompts | Post-hackathon production v2 |
| pgvector / Chroma / Milvus | External DB unnecessary when FAISS in-memory works | If knowledge exceeds 1M chunks |
| BM25 (Okapi variant) | TF-IDF sufficient; BM25 adds length normalization | When doc sizes vary 10x+ |
| Embedding model fine-tuning | MiniLM general-purpose is good enough | When domain accuracy matters |
| Async embedding pipeline | Startup embedding fast for 47 docs | When knowledge exceeds 1000 docs |
| FAISS IVF/HNSW approximate indexes | Exact search fine under 50K vectors | When chunks exceed 50K |

---

## 12. Architecture Diagram (Final State)

```
Browser Extension
       |
       v POST /api/scan
+--------------------------------------------------------------+
|  routes.py                                                   |
|                                                              |
|  1. Presidio (~20ms)                                         |
|     -- PII/secrets detection + masking                       |
|                                                              |
|  2. Pre-Classifier                                           |
|     +-- Secrets found? -> SKIP LLM (policy BLOCKs)          |
|     +-- PII only, no enterprise signal? -> SKIP LLM (MASK)  |
|     |                                                        |
|     +-- Lexical Engine / TF-IDF (less than 1ms)              |
|     |   +-- Inverted index lookup                            |
|     |   +-- IDF-weighted scoring                             |
|     |   +-- Verdict: PUBLIC / AMBIGUOUS / ENTERPRISE_LIKELY  |
|     |                                                        |
|     +-- PUBLIC? -> SKIP LLM (ALLOW)                          |
|     +-- ENTERPRISE_LIKELY? -> SKIP LLM (build ECI, policy)  |
|     |                                                        |
|     +-- AMBIGUOUS? -> Semantic Engine (~50ms)                |
|         +-- Embed prompt (MiniLM local CPU)                  |
|         +-- FAISS top-k search                               |
|         +-- Hybrid score (0.4*lex + 0.6*sem)                 |
|         +-- Confident? -> SKIP LLM                           |
|            Still ambiguous? -> CALL LLM (only ~5% of reqs)   |
|                                                              |
|  3. LLM Router (rare, only true ambiguity)                   |
|     +-- Gemini / Groq / Bedrock / Ollama with fallback       |
|                                                              |
|  4. Policy Engine (less than 1ms)                            |
|     +-- rules.json -> ALLOW / WARN / MASK / BLOCK            |
+--------------------------------------------------------------+
       |
       v
Browser Extension (review modal)
```

---

## 13. Files Modified/Created Summary

| Action | File | Description |
|--------|------|-------------|
| CREATE | backend/ai/lexical_engine.py | Inverted index + TF-IDF scoring |
| CREATE | backend/ai/semantic_engine.py | MiniLM embeddings + FAISS search |
| CREATE | backend/ai/index/ (directory) | Persisted FAISS index + chunk metadata |
| UPDATE | backend/ai/pre_classifier.py | New routing logic using both engines |
| UPDATE | backend/ai/prompt_builder.py | Accept semantic chunks for LLM context |
| UPDATE | backend/config.py | New threshold + engine config vars |
| UPDATE | backend/.env.example | New config documentation |
| UPDATE | backend/requirements.txt | Add sentence-transformers, faiss-cpu |
| DEPRECATE | backend/ai/keyword_search.py | Kept for rollback, no longer imported |
| UPDATE | backend/routes.py | Minor if pre_classifier interface changes |
