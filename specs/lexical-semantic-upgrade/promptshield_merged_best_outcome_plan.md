# PromptShield Merged Plan
## Fast Lexical Gate + Semantic Retrieval + LLM Only for Ambiguity

## 1. Goal

Build a cost-efficient prompt classification pipeline for browser-intercepted AI prompts that:

- detects PII and secrets early
- avoids unnecessary LLM calls
- uses lexical checks for cheap first-pass routing
- uses vector search for semantic relevance when needed
- keeps policy decisions deterministic and explainable

The best outcome is to combine both ideas:

- **their plan**: semantic vector search with FAISS for meaning-based retrieval
- **our plan**: a cheap middleware gate before semantic retrieval to reduce cost and latency

---

## 2. Problem We Are Solving

Current keyword matching is too noisy because generic public tech terms can appear inside enterprise docs and trigger false relevance scores.

That causes:
- public prompts to look enterprise-related
- unnecessary vector/LLM escalation
- wasted tokens and slower response time
- lower precision in the pre-classifier gate

The solution is not to remove semantic search.  
The solution is to place semantic search behind a much cheaper gate.

---

## 3. Recommended Target Architecture

```text
Browser Extension
    ↓
FastAPI /api/scan
    ↓
Presidio + Regex
    ↓
Lexical Relevance Middleware
    ├── normalization
    ├── stopword + generic-tech filtering
    ├── BM25 / FTS5 / inverted index scoring
    ├── document-frequency downweighting
    └── confidence routing
    ↓
Semantic Retrieval Layer
    ├── embeddings (MiniLM or similar)
    ├── FAISS / pgvector / Chroma
    └── top-k relevant chunks
    ↓
Policy Engine
    ↓
LLM Router only for ambiguity
    ↓
Final ALLOW / WARN / MASK / BLOCK
```

---

## 4. Layer Responsibilities

### 4.1 Presidio and Regex
This stays first because it is fast and already working well.

Responsibilities:
- detect PII
- detect secrets
- detect sensitive identifiers
- return strong signals without any retrieval cost

If Presidio is decisive, no retrieval layer is needed.

---

### 4.2 Lexical Relevance Middleware
This is the main cost-saving layer.

Responsibilities:
- normalize prompt text
- remove common public tech vocabulary
- score exact terms and phrases
- downweight tokens that appear in many enterprise docs
- decide whether the prompt is clearly public, clearly enterprise, or ambiguous

This layer should be fast enough to run on every request.

Recommended outputs:
- `PUBLIC`
- `ENTERPRISE_LIKELY`
- `AMBIGUOUS`

Only `AMBIGUOUS` should continue.

---

### 4.3 Semantic Retrieval Layer
This is where your team’s FAISS idea fits best.

Responsibilities:
- embed the prompt
- search the enterprise knowledge base semantically
- retrieve top-k relevant chunks
- improve matching for synonyms and paraphrases

This should not run for every prompt.  
It should run only when lexical scoring is not enough.

---

### 4.4 Policy Engine
The policy engine remains deterministic.

Responsibilities:
- combine Presidio output
- combine lexical relevance
- combine semantic similarity
- produce the final risk score
- apply rules.json decisions

This keeps the system explainable and demo-friendly.

---

### 4.5 LLM Router
The LLM is the last and most expensive layer.

It should be used only when:
- lexical signal is borderline
- semantic retrieval is borderline
- the prompt is enterprise-adjacent but unclear

This is the best place to use Gemini, Groq, Bedrock, or Ollama with fallback.

---

## 5. Retrieval Strategy

### 5.1 Lexical First
Use a fast lexical engine such as:
- SQLite FTS5
- BM25
- Lucene
- inverted-index search

This is better than raw keyword overlap because it:
- ranks relevant terms more intelligently
- reduces false matches on common words
- scales cleanly for your current document count

### 5.2 Vector Second
Use a vector database such as:
- FAISS
- pgvector
- Chroma
- Milvus

This helps when:
- prompts and docs use different wording
- semantic similarity matters more than exact keywords
- you want better retrieval quality than keyword search alone

### 5.3 Hybrid Scoring
Use both signals together:

```text
final_relevance = lexical_score + semantic_score_weighted
```

Then route by thresholds.

---

## 6. Threshold Logic

A practical routing design:

- **Low score** → treat as public, skip vector search and LLM
- **Medium score** → run semantic retrieval, still avoid LLM if confidence improves
- **High score** → enterprise likely, continue policy evaluation
- **Borderline score** → allow LLM router to resolve ambiguity

This is the key cost control mechanism.

---

## 7. Data Structures

### 7.1 Lexical index
Store:
- token
- document frequency
- term frequency
- phrase positions
- document IDs

### 7.2 Vector index
Store:
- embedding
- chunk text
- source file
- section heading
- metadata tags

### 7.3 Prompt cache
Store:
- normalized prompt hash
- lexical score
- semantic score
- final decision
- timestamp

This helps avoid repeat cost for repeated prompts.

---

## 8. Why This Merged Plan Is Better

### Better than keyword-only
Because it uses semantic retrieval for synonyms and paraphrases.

### Better than vector-only
Because it avoids embedding and search cost for obviously public prompts.

### Better than always calling the LLM
Because most prompts should be resolved before any model call.

### Better than static stopwords alone
Because corpus statistics and document frequency automatically reduce noise.

This gives you the best balance of:
- cost
- latency
- accuracy
- explainability

---

## 9. Implementation Phases

### Phase 1: Build the lexical middleware
- normalize prompts
- compute corpus statistics
- apply generic tech filtering
- create relevance thresholds

### Phase 2: Add semantic retrieval
- embed knowledge docs
- build FAISS or equivalent index
- retrieve top-k chunks only for ambiguous prompts

### Phase 3: Add routing control
- merge lexical and semantic scores
- define confidence bands
- call the LLM only when ambiguity remains

### Phase 4: Optimize cost and stability
- add prompt cache
- log routing decisions
- tune thresholds with real prompts
- measure false positives and LLM call reduction

---

## 10. Success Criteria

The merged plan is successful if:

- LLM calls drop significantly
- general public prompts no longer trigger enterprise routing
- semantic matching still catches internal synonym cases
- policy decisions stay deterministic
- browser-extension response time remains fast enough for demo use

---

## 11. Example Routing

### Prompt
> Tell me how Amazon Web Services work

Expected behavior:
- Presidio: no PII or secrets
- lexical middleware: generic public tech vocabulary only
- semantic retrieval: low enterprise similarity
- LLM router: skipped
- policy engine: treat as public/general

### Prompt
> Our transaction gateway stores customer PAN in Oracle

Expected behavior:
- Presidio: PAN detected
- lexical middleware: enterprise terms present
- semantic retrieval: likely strong match
- policy engine: high risk
- final action: warn or block depending on rules

---

## 12. Final Recommendation

Use this merged stack:

**Presidio + lexical middleware + semantic retrieval + deterministic policy engine + LLM only for ambiguity**

That is the best outcome for the hackathon product because it is:
- cheaper
- faster
- more accurate
- easier to explain
- strong enough for an end-to-end demo
