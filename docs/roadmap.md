# Roadmap

Status snapshot of PromptShield AI (hackathon research repo). "Done" means implemented
and present in this repo as of this writing — see [`architecture.md`](architecture.md)
for how these pieces fit together, and each folder's own README for detail.

## Done

- **Backend detection API** (`backend/`) — FastAPI service with `/health`, `/analyze`
  (Presidio-only), and `/api/scan` (full pipeline).
- **Presidio + custom recognizers** — PAN, Aadhaar, passport, driving license, GSTIN,
  employee ID, IFSC, UPI ID, bank account, host name, MAC address, vehicle number, and
  secret/credential detectors (GitHub token, OpenAI key, AWS keys, JWT, private key).
- **Policy Engine** — deterministic `rules.json`-driven ALLOW/WARN/MASK/BLOCK decision
  with an explainable 0–100 aggregate risk score.
- **Enterprise Context Intelligence (ECI)** — LLM-based classification of intent,
  document type, and compliance-framework impact (GDPR/PCI-DSS/HIPAA/ISO 27001) against
  the `knowledge/` base, with a fail-closed default when the LLM is unreachable.
- **Smart LLM Router** — `local`/`cloud`/`auto` routing across Ollama (local), Groq,
  Google Gemini, and Amazon Bedrock, with fallback-to-local on cloud failure.
- **Lexical + semantic pre-classifier** — TF-IDF inverted-index scoring plus a
  FAISS/MiniLM semantic tier that resolves most prompts without an LLM call (see
  [`specs/lexical-semantic-upgrade/`](../specs/lexical-semantic-upgrade/) for the spec
  this shipped from).
- **Browser extension** (`browser-extension/`) — Manifest V3 extension covering
  ChatGPT, Gemini, Claude, DeepSeek, and Copilot/Bing Chat, with send interception, a
  review modal (issues + AI context analysis), and fail-open behavior if the API is
  unavailable.
- **Fictional enterprise knowledge base** (`knowledge/`) — "NovaBank" content across
  APIs, architecture, compliance, data, engineering, governance, operations,
  organization, products, and support, used as retrieval context.
- **Property-based test suite** (`tests/`) — Hypothesis property tests for the
  lexical/semantic/hybrid-scoring/routing logic, plus integration tests and a manual
  ECI smoke test.

## In progress / next up

- **Regex pattern-matching layer** — a dedicated `backend/regex/` module is referenced
  in design docs but not yet built; Presidio currently covers this ground.
- **Wire `PROMPTSHIELD_PRESIDIO_MIN_SCORE`** into `presidio_engine.py`, which currently
  hardcodes its own threshold instead of reading the env var.
- **Close known detection gaps** documented in `tests/test_scenarios.md`:
  - `BANK_ACCOUNT` pattern score is currently unreachable under Presidio's score filter
  - lone `HOST_NAME`/`MAC_ADDRESS` findings resolve to `ALLOW` instead of `MASK`/`WARN`
  - the risk-80 aggregate `BLOCK` threshold may be too aggressive for PII-only
    combinations (worth a product decision, not just a bug fix)
- **Compliance-schema reliability** — growing the ECI schema to 14 required fields
  measurably increases malformed output from `phi3:mini`; consider a larger/
  instruction-tuned model or splitting compliance mapping into its own lighter call.
- **Populate `samples/`** (`blocked_prompts/`, `safe_prompts/`, `warning_prompts/`,
  `expected_results/`) so `tests/test_pipeline_e2e.py` has real fixtures to run against.
- **Finish `scripts/run_demo.sh` and `scripts/seed_knowledge.py`** — currently stub
  files with only a header comment describing intent.

## Post-MVP / future

- Persist decisions to an audit log (currently only visible via server logs and the
  per-request API response).
- Per-destination or per-user policy differentiation (e.g. stricter rules for public
  chat sites than for an internal tool).
- Prompt-result caching for repeated/similar prompts.
- Swap FAISS `IndexFlatIP` (exact search) for an approximate index (IVF/HNSW) if the
  knowledge base grows past ~50K chunks.
- Fine-tune or swap the embedding/classification models for domain accuracy once real
  usage data is available.
