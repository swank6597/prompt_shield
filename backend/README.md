# PromptShield Detection API

FastAPI backend for PromptShield. It scans user prompts for sensitive data using a multi-layered detection pipeline: Microsoft Presidio (PII), Enterprise Context Intelligence (semantic classification via LLM), and a Policy/Risk Engine that produces the final ALLOW/WARN/MASK/BLOCK decision.

## Overview

The backend runs the full detection pipeline:

1. Accept a prompt from the browser extension (`/api/scan`)
2. **Presidio** detects PII and custom enterprise entities, masks them
3. **Pre-Classifier** (`ai/pre_classifier.py`) runs a three-tier lexical (TF-IDF) + semantic (FAISS/MiniLM) gate that resolves most prompts — trivial, secret, PII-only, public, or clearly-enterprise — **without an LLM call**; only genuinely ambiguous prompts are escalated
4. **ECI Semantic Classifier** (only for escalated prompts) sends the masked prompt + retrieved enterprise knowledge to an LLM for context-aware classification
5. **Policy Engine** combines Presidio findings + ECI classification into a final risk decision
6. Return `SAFE`, `WARN`, `SANITIZE`, or `BLOCK` with issue details to the extension

See [`ai/README.md`](ai/README.md) for the full pre-classifier/ECI pipeline and [`policy/README.md`](policy/README.md) for the decision layer.

## Requirements

- Python 3.11 recommended (Presidio has compatibility issues on 3.12.7+)
- pip
- At least one LLM provider (local Ollama OR a cloud API key)

## Quick Start

### Option A: One-click launcher (recommended)

From the repo root, double-click `start-backend.bat` or run:

```powershell
.\start-backend.ps1
```

This creates the venv, installs deps, and starts uvicorn with logs streaming to the console.

### Option B: Manual setup

**Windows (PowerShell):**
```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m spacy download en_core_web_lg
uvicorn app:app --reload --port 8081
```

**macOS / Linux:**
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_lg
uvicorn app:app --reload --port 8081
```

Notes:
- Use port `8081` by default. Port `8080` is often already used on Windows.
- Health check: `http://localhost:8081/health`

## Configuration (.env)

All configuration and secrets are loaded from `backend/.env` (never committed to git).

**First-time setup:**
```powershell
Copy-Item .env.example .env
# Then edit .env with your values
```

The `.env.example` file documents every available setting (28 variables total, all read in `config.py` via `os.environ.get()` with the `.env` file as a fallback, real OS/environment variables always win). Most commonly changed:

| Variable | Default | Description |
|---|---|---|
| `PROMPTSHIELD_LLM_STRATEGY` | `local` | Routing strategy: `local`, `cloud`, or `auto` |
| `PROMPTSHIELD_LLM_CLOUD_PROVIDER` | `groq` | Cloud provider: `groq`, `gemini`, or `bedrock` |
| `PROMPTSHIELD_GROQ_API_KEY` | *(empty)* | Groq API key ([get free key](https://console.groq.com/keys)) |
| `PROMPTSHIELD_GEMINI_API_KEY` | *(empty)* | Google Gemini key ([get free key](https://aistudio.google.com/apikey)) |
| `PROMPTSHIELD_OLLAMA_MODEL` | `phi3:mini` | Local Ollama model name |
| `PROMPTSHIELD_LLM_FALLBACK_TO_LOCAL` | `true` | Fall back to Ollama if cloud fails |
| `PROMPTSHIELD_USE_LEGACY_SEARCH` | `false` | Bypass the lexical/semantic engines and use the old `keyword_search.py` overlap scoring |

The remaining variables tune the pre-classifier and are documented inline in `.env.example`:

| Group | Variables |
|---|---|
| Presidio | `PROMPTSHIELD_PRESIDIO_MIN_SCORE` *(currently unused — `presidio_engine.py` hardcodes its own `MIN_SCORE`, see Known Limitations)* |
| Lexical engine (TF-IDF) | `PROMPTSHIELD_TFIDF_PUBLIC_THRESHOLD` (0.15), `PROMPTSHIELD_TFIDF_ENTERPRISE_THRESHOLD` (0.45) |
| Semantic engine (FAISS) | `PROMPTSHIELD_EMBEDDING_MODEL` (`all-MiniLM-L6-v2`), `PROMPTSHIELD_SEMANTIC_CHUNK_SIZE` (500) |
| Hybrid scoring | `PROMPTSHIELD_HYBRID_LEXICAL_WEIGHT` (0.4), `PROMPTSHIELD_HYBRID_SEMANTIC_WEIGHT` (0.6), `PROMPTSHIELD_HYBRID_PUBLIC_THRESHOLD` (0.30), `PROMPTSHIELD_HYBRID_ENTERPRISE_THRESHOLD` (0.55) |
| Ollama | `PROMPTSHIELD_OLLAMA_HOST`, `PROMPTSHIELD_OLLAMA_TIMEOUT`, `PROMPTSHIELD_OLLAMA_MAX_RETRIES` |
| Groq / Gemini / Bedrock | `PROMPTSHIELD_GROQ_MODEL`/`_TIMEOUT`, `PROMPTSHIELD_GEMINI_MODEL`/`_TIMEOUT`, `PROMPTSHIELD_BEDROCK_REGION`/`_MODEL_ID`/`_TIMEOUT` |
| Auto-routing | `PROMPTSHIELD_LLM_AUTO_LENGTH_THRESHOLD` (50), `PROMPTSHIELD_LLM_AUTO_ENTITY_THRESHOLD` (3) |

See [Lexical + Semantic Pre-Classification](#lexical--semantic-pre-classification) below for how the TF-IDF/hybrid thresholds are used.

## Lexical + Semantic Pre-Classification

Before any LLM call is considered, `ai/pre_classifier.py` runs a fast, deterministic gate (`routes.py` calls `pre_classify()` right after Presidio):

1. **Trivial check** — small-talk / empty prompts with zero Presidio entities skip everything (`decision_path=trivial`)
2. **Secrets check** — any secret entity type (`GITHUB_TOKEN`, `OPENAI_API_KEY`, `AWS_ACCESS_KEY`, `AWS_SECRET_KEY`, `PRIVATE_KEY`, `JWT_TOKEN`) skips the LLM and goes straight to a hard-block decision (`decision_path=hard_block`)
3. **Lexical tier** (`ai/lexical_engine.py`) — an in-memory TF-IDF inverted index built from `knowledge/` at startup scores the prompt in under 1ms:
   - `PUBLIC` (score `< PROMPTSHIELD_TFIDF_PUBLIC_THRESHOLD`, default 0.15) → skip LLM (`pii_only` if PII was found, else `general_knowledge`)
   - `ENTERPRISE_LIKELY` (score `>= PROMPTSHIELD_TFIDF_ENTERPRISE_THRESHOLD`, default 0.45) → skip LLM (`enterprise_detected`)
   - `AMBIGUOUS` (in between) → escalate to the semantic tier
4. **Semantic tier** (`ai/semantic_engine.py`, only for `AMBIGUOUS` prompts) — embeds the prompt with a local `sentence-transformers` model and searches a FAISS index of chunked `knowledge/` docs (~50ms), then computes a hybrid score: `PROMPTSHIELD_HYBRID_LEXICAL_WEIGHT * tfidf + PROMPTSHIELD_HYBRID_SEMANTIC_WEIGHT * semantic`
   - `< PROMPTSHIELD_HYBRID_PUBLIC_THRESHOLD` (default 0.30) → skip LLM (`semantic_confirmed_public`)
   - `>= PROMPTSHIELD_HYBRID_ENTERPRISE_THRESHOLD` (default 0.55) → skip LLM (`semantic_confirmed_enterprise`)
   - otherwise → **call the LLM** (`true_ambiguity` — the only path that reaches ECI/the LLM Router)

This is what actually keeps the LLM call rate low, not just the trivial-prompt check. Setting `PROMPTSHIELD_USE_LEGACY_SEARCH=true` reverts to the older raw-token-overlap scoring in `keyword_search.py` (kept for rollback) instead of the lexical/semantic engines. The FAISS index and chunk metadata are persisted to `ai/index/` (git-ignored) and only rebuilt when a `knowledge/` file's modification time changes. See [`ai/README.md`](ai/README.md) and [`../specs/lexical-semantic-upgrade/design.md`](../specs/lexical-semantic-upgrade/design.md) for full design details.

## Smart LLM Router

The router decides which LLM provider handles each classification request. This solves the problem of running on machines without a dedicated GPU — you can route to fast cloud APIs instead of waiting 30-180s for a local CPU inference.

### Routing Strategies

| Strategy | Behavior |
|---|---|
| `local` | Always use local Ollama (default, original behavior) |
| `cloud` | Always use the configured cloud provider |
| `auto` | Route dynamically per-request based on complexity |

### Auto-Routing Heuristics

When `PROMPTSHIELD_LLM_STRATEGY=auto`, the router analyzes each request:

| Signal | Threshold | Effect |
|---|---|---|
| Prompt word count | > 50 words | Route to cloud (faster) |
| Presidio entity count | > 3 entities | Route to cloud (complex classification) |
| Complexity keywords | >= 2 hits | Route to cloud (needs better model) |

If none of these trigger, the prompt goes to local Ollama (cheap, no network needed).

Complexity keywords include: `architecture`, `oauth`, `encryption`, `database`, `kubernetes`, `compliance`, `api key`, `secret`, `credential`, etc.

### Available Providers

| Provider | Config Key | Free Tier | Speed |
|---|---|---|---|
| **Ollama** (local) | `local` | Unlimited (runs locally) | Slow on CPU (~30-180s) |
| **Groq** | `groq` | 30 req/min | Very fast (~1-3s) |
| **Google Gemini** | `gemini` | 15 req/min | Fast (~2-5s) |
| **Amazon Bedrock** | `bedrock` | Pay-per-use (AWS) | Fast (~2-5s) |

### Example Configurations

**Fastest free option (Groq):**
```ini
PROMPTSHIELD_LLM_STRATEGY=cloud
PROMPTSHIELD_LLM_CLOUD_PROVIDER=groq
PROMPTSHIELD_GROQ_API_KEY=gsk_your_key_here
```

**Google Gemini:**
```ini
PROMPTSHIELD_LLM_STRATEGY=cloud
PROMPTSHIELD_LLM_CLOUD_PROVIDER=gemini
PROMPTSHIELD_GEMINI_API_KEY=your_key_here
```

**Smart auto-routing (short prompts local, complex prompts cloud):**
```ini
PROMPTSHIELD_LLM_STRATEGY=auto
PROMPTSHIELD_LLM_CLOUD_PROVIDER=groq
PROMPTSHIELD_GROQ_API_KEY=gsk_your_key_here
```

**Local only (no internet needed):**
```ini
PROMPTSHIELD_LLM_STRATEGY=local
PROMPTSHIELD_OLLAMA_MODEL=phi3:mini
```

### Adding a New Provider

The provider registry is fully dynamic. To add a new provider (e.g. OpenAI, Mistral):

1. Create `backend/ai/providers/my_provider.py` with:
   - `name` class attribute (the config key, e.g. `"openai"`)
   - `call(system_prompt, user_prompt) -> str` method
   - `is_available() -> bool` method
2. Import it in `backend/ai/providers/__init__.py` and add to `PROVIDER_CLASSES`
3. Add its config vars to `config.py` and `.env.example`

No changes to `llm_router.py` or `semantic_classifier.py` needed.

## Endpoints

### `GET /health`

Returns service status.

### `POST /analyze`

Presidio-only analysis endpoint (direct testing and tooling).

Request:
```json
{ "text": "My email is john.doe@example.com" }
```

Response:
```json
{
  "success": true,
  "entityCount": 1,
  "maskedText": "My email is <EMAIL_ADDRESS>",
  "entities": [
    {
      "entity_type": "EMAIL_ADDRESS",
      "value": "john.doe@example.com",
      "score": 1.0,
      "start": 12,
      "end": 32
    }
  ]
}
```

### `POST /api/scan`

Primary endpoint used by the browser extension. Runs the full pipeline (Presidio + Smart Router + ECI + Policy Engine).

**Requires an `X-API-Key` header** (see [Authentication](#authentication) below) -
requests without one, or with an unknown/revoked key, get `401 Unauthorized` before
the pipeline runs.

Request:
```json
{ "prompt": "My email is john.doe@example.com and my phone is 555-123-4567" }
```

Response when sensitive data is found:
```json
{
  "status": "SANITIZE",
  "sanitizedPrompt": "My email is <EMAIL_ADDRESS> and my phone is <PHONE_NUMBER>",
  "reason": "Detected 2 sensitive item(s): EMAIL_ADDRESS, PHONE_NUMBER",
  "issues": [
    { "entityType": "EMAIL_ADDRESS", "value": "john.doe@example.com", "score": 1.0 },
    { "entityType": "PHONE_NUMBER", "value": "555-123-4567", "score": 0.85 }
  ],
  "eci": { "intent": "DataSharing", "confidence": 0.92, "..." : "..." },
  "riskScore": 75,
  "matchedRules": ["pii_detected", "high_entity_count"]
}
```

Response when no sensitive data is found:
```json
{
  "status": "SAFE",
  "sanitizedPrompt": "Hello world",
  "issues": [],
  "riskScore": 0,
  "matchedRules": []
}
```

## Status Values

| Status | Policy decision | Meaning |
|---|---|---|
| `SAFE` | ALLOW | No risk detected — prompt can be sent as-is |
| `WARN` | WARN | Enterprise-context risk flagged, but no entities were masked — nothing to sanitize, review and choose to send or cancel |
| `SANITIZE` | MASK | PII/secrets detected and masked — a sanitized prompt is available to send instead of the original |
| `BLOCK` | BLOCK | High-risk content — policy engine blocks the prompt entirely |

## Authentication

See [`specs/authentication/`](../specs/authentication/) for the full design. Summary:

- **`/api/scan` requires an `X-API-Key` header.** Enroll a device first:
  `POST /devices/enroll {"label": "my-laptop"}` → returns `apiKey` once (it is
  never retrievable again - store it in the extension's local storage).
- **`/auth/*` and `/devices/*`** (except `/devices/enroll`) require a dashboard user
  session: `POST /auth/login {"username": "...", "password": "..."}` → returns a
  bearer `accessToken`, sent as `Authorization: Bearer <token>` on subsequent calls.
  Device-management endpoints (`GET /devices`, `POST /devices/{id}/revoke`,
  `GET /auth/audit-log`) additionally require the `admin` role.
- **No self-service signup.** Create the first admin account with
  `python scripts/create_admin.py` (see that script's `--help`).
- **Config:** `PROMPTSHIELD_AUTH_SECRET_KEY` is required (no safe default - the
  backend refuses to start without it); see `.env.example` for the full list of
  `PROMPTSHIELD_AUTH_*` settings.
- These route groups are mounted as separate sub-apps in `app.py` so
  `/auth/*`/`/devices/*`/`/dashboard/*` can have a different (non-wildcard) CORS
  policy than `/api/scan` - each has its own Swagger page, not one shared `/docs`:

  | Swagger page | Covers |
  |---|---|
  | `/docs` | the scan API itself (`/health`, `/analyze`, `/api/scan`) |
  | `/auth/docs` | `/auth/login`, `/logout`, `/me`, `/audit-log` |
  | `/devices/docs` | `/devices/enroll`, list, `/{id}/revoke` |

  Each endpoint uses a real FastAPI security scheme (`APIKeyHeader`/`HTTPBearer`,
  not a raw header param), so every page shows a working 🔒 **Authorize** button -
  paste just the raw token/key, no need to type `Bearer <token>` yourself.
  **Authorizing on one page does not carry over to another** (three independent
  sub-apps, three independent OpenAPI schemas/auth states) - e.g. authorize on
  `/auth/docs` to log in, then authorize *again* with the same `accessToken` on
  `/devices/docs` before calling `/enroll`, so the enrolled device gets linked to
  your user account (`ownerUserId`) rather than created anonymously.

## Dashboard

Visual, read-only view over the audit trail - `http://localhost:8081/dashboard/`.
Signs in with the same accounts as above (any role, `admin` or `viewer`). See
[`dashboard/README.md`](dashboard/README.md) for the module layout, API, and a note
on where the styling came from (matched to `browser-extension/`'s existing dark
theme, not a generic palette).

## Project Structure

```
backend/
├── app.py                     # FastAPI entrypoint
├── config.py                  # Centralized config (loads from .env)
├── routes.py                  # HTTP routes + orchestration
├── models.py                  # Request/response Pydantic models
├── requirements.txt           # Python dependencies
├── .env                       # Secrets (git-ignored, never committed)
├── .env.example               # Template for .env (safe to commit)
├── ai/                        # Pre-classification + semantic classification layer
│   ├── pre_classifier.py      # Three-tier lexical/semantic gate (see above)
│   ├── lexical_engine.py      # TF-IDF inverted-index scoring
│   ├── semantic_engine.py     # MiniLM embeddings + FAISS search
│   ├── index/                 # Persisted FAISS index + chunk metadata (git-ignored, built on demand)
│   ├── llm_router.py          # Smart LLM Router (strategy + fallback)
│   ├── semantic_classifier.py # ECI orchestrator (retrieval + LLM + validation)
│   ├── prompt_builder.py      # Assembles system/user prompts
│   ├── keyword_search.py      # Legacy enterprise knowledge retrieval (kept for PROMPTSHIELD_USE_LEGACY_SEARCH rollback)
│   ├── context_loader.py      # Walks knowledge/ into memory
│   ├── ollama_client.py       # Low-level Ollama HTTP client
│   ├── schema.json            # LLM output validation schema
│   ├── prompts/               # System + classifier prompt templates
│   └── providers/             # LLM provider implementations
│       ├── __init__.py        # Dynamic provider registry
│       ├── ollama_provider.py # Local Ollama (wraps ollama_client.py)
│       ├── groq_provider.py   # Groq cloud API (free tier)
│       ├── gemini_provider.py # Google Gemini (free tier)
│       └── bedrock_provider.py# Amazon Bedrock (AWS)
├── presidio/                  # Presidio analyzer + custom recognizers
│   ├── presidio_engine.py
│   └── recognizers/           # Banking, personal, infrastructure, security
├── policy/                    # Policy + risk engine
│   ├── policy_engine.py
│   ├── risk_engine.py
│   └── rules.json             # Configurable policy rules
├── audit/                     # Audit trail - see audit/README.md
│   ├── audit_logger.py        # log_scan() - the only writer to scan_audit_log
│   └── audit_log.db           # SQLite (git-ignored, created on first run)
├── auth/                      # Device/user authentication - see specs/authentication/
├── dashboard/                 # Visual audit-trail UI - see dashboard/README.md
│   ├── queries.py             # Read-only queries over scan_audit_log
│   ├── routes.py              # GET /api/stats, GET /api/events
│   └── static/                # index.html + style.css + app.js (no build step)
└── utils/                     # Logger, helpers
```

Note: a dedicated `regex/` pattern-matching layer is planned but not yet created — Presidio's built-in + custom recognizers currently cover that ground (see Known Limitations).

## Custom Recognizers

Custom entity detection lives under `presidio/recognizers/`, registered via `registry.py`:

| Module | Entity types |
|---|---|
| `personal.py` | `PAN_NUMBER`, `AADHAAR_NUMBER`, `PASSPORT_NUMBER`, `DRIVING_LICENSE`, `GSTIN`, `EMPLOYEE_ID`, `PHONE_NUMBER` (US format) |
| `banking.py` | `IFSC_CODE`, `UPI_ID`, `BANK_ACCOUNT` |
| `infrastructure.py` | `HOST_NAME`, `MAC_ADDRESS` |
| `security.py` | `OPENAI_API_KEY`, `GITHUB_TOKEN`, `JWT_TOKEN`, `AWS_ACCESS_KEY`, `AWS_SECRET_KEY`, `PRIVATE_KEY` (PEM block) |
| `custom_recognizers.py` | `VEHICLE_NUMBER` |

IP addresses are caught by Presidio's built-in `IP_ADDRESS` recognizer, not a custom one. There is no dedicated connection-string or certificate recognizer today — `PRIVATE_KEY`'s PEM-block pattern is the closest match for the latter.

## Architecture Flow

```
Browser Extension
       │
       ▼ POST /api/scan
┌────────────────────────────────────────────────────────────────┐
│  routes.py (Orchestrator)                                      │
│                                                                  │
│  1. Presidio ──► detect + mask PII                               │
│  2. Pre-Classifier (lexical TF-IDF + semantic FAISS, 3 tiers)    │
│       trivial / secrets / PUBLIC / ENTERPRISE_LIKELY ─► skip LLM │
│       AMBIGUOUS ─► escalate                                      │
│  3. ECI Classifier (only if escalated) ──► LLM Router ──► Provider│
│     ├── local (Ollama)                                          │
│     ├── groq (Groq API)                                         │
│     ├── gemini (Google Gemini)                                  │
│     └── bedrock (Amazon Bedrock)                                 │
│  4. Policy Engine ──► rules.json ──► ALLOW/WARN/MASK/BLOCK        │
│                                                                  │
└────────────────────────────────────────────────────────────────┘
       │
       ▼ { status, sanitizedPrompt, issues, riskScore }
Browser Extension (shows review modal)
```

## Related Docs

- Root setup guide: [`../README.md`](../README.md)
- Browser extension: [`../browser-extension/README.md`](../browser-extension/README.md)
- Architecture: [`../docs/architecture.md`](../docs/architecture.md)

## Known Limitations

- Local Ollama (phi3:mini on CPU) takes 30-180s per classification — use `strategy=cloud` or `strategy=auto` for demos. Thanks to the pre-classifier, most requests never hit this path at all.
- phi3:mini occasionally produces malformed JSON on the 14-field schema — the classifier retries once then falls back to a fail-closed WARN
- Groq/Gemini free tiers have rate limits (30/15 req/min) — sufficient for demo use, not production traffic
- A dedicated Regex pattern-matching layer is not yet built — there is no `backend/regex/` folder; Presidio's built-in and custom recognizers currently cover PII/secret pattern matching
- `PROMPTSHIELD_PRESIDIO_MIN_SCORE` in `.env.example` is currently not read by `presidio_engine.py`, which hardcodes its own `MIN_SCORE = 0.85` — changing the env var has no effect yet
- `BANK_ACCOUNT` (banking.py) has a low base pattern score and is effectively unreachable under the current Presidio score threshold — see `tests/test_scenarios.md` section A5
- `HOST_NAME`/`MAC_ADDRESS` aren't in the `mask_personal_identifiers` rule, so a lone occurrence currently resolves to `ALLOW` instead of `MASK`/`WARN` — see `tests/test_scenarios.md` section A4
