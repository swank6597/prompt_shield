# Architecture

System architecture for PromptShield: a browser extension that intercepts prompts on
public AI chat sites and a local FastAPI backend that scans them for PII, secrets, and
enterprise-sensitive content before they're sent.

For setup instructions see the [root README](../README.md); for endpoint-level detail
see [`backend/README.md`](../backend/README.md).

## Components

```
┌────────────────────────┐        ┌──────────────────────────────────────────────┐
│  Browser Extension       │ POST  │  Backend (FastAPI, localhost:8081)           │
│  (Manifest V3)            │───────▶  routes.py                                    │
│                            │       │                                                │
│  content.js → detector.js │       │  1. Presidio          detect + mask PII        │
│  → observer.js intercepts  │       │  2. Pre-Classifier     lexical + semantic gate │
│  send, api-client.js →     │       │  3. ECI (conditional)  LLM classification      │
│  background.js → fetch     │       │  4. Policy Engine      rules.json → decision   │
│                            │◀──────│                                                │
│  modal.js shows review UI │ JSON  │  { status, sanitizedPrompt, issues, riskScore } │
└────────────────────────┘        └──────────────────────────────────────────────┘
```

### Browser extension (`browser-extension/`)

Manifest V3 extension ("Prompt Guardian"). Runs on ChatGPT, Gemini, Claude, DeepSeek,
and Copilot/Bing Chat (see [`browser-extension/README.md`](../browser-extension/README.md)
for the exact domain list). Responsibilities:

- `content/detector.js` finds the active prompt composer and send control per site,
  using site-specific selectors (`site-definitions.js`) plus generic scoring heuristics
  and shadow-DOM traversal as a fallback.
- `content/observer.js` intercepts Enter, the send button, and form submits; on
  intercept it calls the scan API and either auto-replays the send (`SAFE`) or opens
  the review modal (`SANITIZE`/`BLOCK`).
- `content/api-client.js` → `background/background.js` → `fetch` is a two-hop path:
  the content script messages the background service worker, which owns the actual
  network call to the backend. Both hops fail open to `SAFE` if the API is unreachable,
  so typing is never blocked by a backend outage during development.
- `content/modal.js` renders the in-page review UI (issues found, sanitized text, and
  an "AI Context Analysis" summary of the ECI classification) in a shadow DOM.
- `popup/` is a separate, static toolbar popup (feature summary only) — not the review UI.

### Backend (`backend/`)

FastAPI service exposing `GET /health`, `POST /analyze` (Presidio-only), and
`POST /api/scan` (full pipeline). See [`backend/README.md`](../backend/README.md) for
the endpoint contracts and configuration reference.

**Detection pipeline for `/api/scan`:**

1. **Presidio** (`presidio/`) — Microsoft Presidio plus custom recognizers (PAN,
   Aadhaar, passport, driving license, GSTIN, employee ID, IFSC, UPI, bank account,
   host name, MAC address, vehicle number, and secret/credential patterns) detects and
   masks entities in the raw prompt.
2. **Pre-Classifier** (`backend/ai/pre_classifier.py`) — a three-tier gate that decides
   whether an LLM call is needed at all, in priority order:
   - trivial small-talk with no entities → skip
   - any secret/credential entity → skip straight to a block signal
   - **lexical tier** (`lexical_engine.py`): TF-IDF over an inverted index built from
     `knowledge/` classifies the prompt `PUBLIC` / `ENTERPRISE_LIKELY` / `AMBIGUOUS`
     in under 1ms; `PUBLIC` and `ENTERPRISE_LIKELY` skip the LLM
   - **semantic tier** (`semantic_engine.py`, only for `AMBIGUOUS`): local
     `sentence-transformers` embeddings + a FAISS index over chunked `knowledge/` docs
     produce a hybrid lexical+semantic score; only prompts that remain ambiguous after
     this (`true_ambiguity`) are escalated to the LLM
   - see [`backend/ai/README.md`](../backend/ai/README.md) and
     [`specs/lexical-semantic-upgrade/design.md`](../specs/lexical-semantic-upgrade/design.md)
     for the full routing logic and thresholds
3. **ECI — Enterprise Context Intelligence** (`backend/ai/semantic_classifier.py`,
   only runs for escalated prompts) — sends the masked prompt plus retrieved
   `knowledge/` context to an LLM (routed via the Smart LLM Router across
   Ollama/Groq/Gemini/Bedrock) for a structured classification against
   `backend/ai/schema.json`: intent, document type, risk flags
   (secrets/source-code/internal-architecture/customer-data), and compliance-framework
   impact (GDPR/PCI-DSS/HIPAA/ISO 27001). Every failure path (provider unreachable,
   invalid output) returns a fail-closed result instead of raising.
4. **Policy Engine** (`backend/policy/`) — `policy_engine.decide()` combines Presidio's
   entity findings with the ECI result (real or pre-classifier-synthesized) against
   declarative rules in `rules.json`, plus an aggregate 0–100 risk score
   (`risk_engine.py`), to produce a final `ALLOW` / `WARN` / `MASK` / `BLOCK` decision.
   Rules are OR'd (not first-match); the highest-severity matching decision wins.

The API maps `ALLOW → SAFE`, `WARN`/`MASK → SANITIZE`, `BLOCK → BLOCK` for the
extension. See [`backend/policy/README.md`](../backend/policy/README.md) for the full
decision table and rule semantics.

### Knowledge base (`knowledge/`)

A fictional "NovaBank" enterprise knowledge base (APIs, architecture, compliance,
data, engineering, governance, operations, organization, products, support — see
[`knowledge/README.md`](../knowledge/README.md)) used only as retrieval context for
the lexical/semantic/ECI layers, never as real company data.

## Data flow example

```
User types "My email is john@example.com" into ChatGPT and presses Enter
  → observer.js intercepts the send
  → api-client.js → background.js → POST /api/scan {"prompt": "..."}
  → Presidio detects EMAIL_ADDRESS, masks it
  → Pre-Classifier: no secrets, PII detected + lexical verdict PUBLIC → skip LLM (pii_only path)
  → Policy Engine: mask_personal_identifiers rule matches → decision MASK, riskScore 5
  → routes.py maps MASK → status "SANITIZE"
  → extension shows the review modal with the sanitized prompt
  → user clicks "Send Sanitized" → composer updated → prompt sent
```

## Known architectural gaps

- No dedicated Regex pattern-matching layer exists yet (`backend/regex/` is planned,
  not built) — Presidio and its custom recognizers currently cover that ground.
- No persistence/audit log of past decisions — results are only visible in server logs
  and the API response for the current request.
- Policy rules are static and global — no per-destination (e.g. ChatGPT vs. an internal
  tool) or per-user policy differentiation yet.
- See `backend/README.md`'s "Known Limitations" and `tests/test_scenarios.md` for
  specific detection gaps (e.g. `BANK_ACCOUNT` currently unreachable, lone
  `HOST_NAME`/`MAC_ADDRESS` resolving to `ALLOW`).
