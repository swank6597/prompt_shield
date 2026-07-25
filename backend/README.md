# PromptShield Detection API

FastAPI backend for Prompt Guardian. It scans user prompts for sensitive data using a multi-layered detection pipeline: Microsoft Presidio (PII), Enterprise Context Intelligence (semantic classification via LLM), and a Policy/Risk Engine that produces the final ALLOW/WARN/MASK/BLOCK decision.

## Overview

The backend runs the full detection pipeline:

1. Accept a prompt from the browser extension (`/api/scan`)
2. **Presidio** detects PII and custom enterprise entities, masks them
3. **Smart Analysis Router** decides whether the expensive LLM call is needed
4. **ECI Semantic Classifier** sends the masked prompt + retrieved enterprise knowledge to an LLM for context-aware classification
5. **Policy Engine** combines Presidio findings + ECI classification into a final risk decision
6. Return `SAFE`, `SANITIZE`, or `BLOCK` with issue details to the extension

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

The `.env.example` file documents every available setting. Key ones:

| Variable | Default | Description |
|---|---|---|
| `PROMPTSHIELD_LLM_STRATEGY` | `local` | Routing strategy: `local`, `cloud`, or `auto` |
| `PROMPTSHIELD_LLM_CLOUD_PROVIDER` | `groq` | Cloud provider: `groq`, `gemini`, or `bedrock` |
| `PROMPTSHIELD_GROQ_API_KEY` | *(empty)* | Groq API key ([get free key](https://console.groq.com/keys)) |
| `PROMPTSHIELD_GEMINI_API_KEY` | *(empty)* | Google Gemini key ([get free key](https://aistudio.google.com/apikey)) |
| `PROMPTSHIELD_OLLAMA_MODEL` | `phi3:mini` | Local Ollama model name |
| `PROMPTSHIELD_LLM_FALLBACK_TO_LOCAL` | `true` | Fall back to Ollama if cloud fails |

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

| Status | Meaning |
|---|---|
| `SAFE` | No risk detected — prompt can be sent as-is |
| `SANITIZE` | Sensitive data detected; sanitized prompt available for review |
| `BLOCK` | High-risk content — policy engine blocks the prompt entirely |

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
├── ai/                        # Semantic classification layer
│   ├── llm_router.py          # Smart LLM Router (strategy + fallback)
│   ├── semantic_classifier.py # ECI orchestrator (retrieval + LLM + validation)
│   ├── prompt_builder.py      # Assembles system/user prompts
│   ├── keyword_search.py      # Enterprise knowledge retrieval
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
├── regex/                     # Regex pattern detection
└── utils/                     # Logger, helpers
```

## Custom Recognizers

Custom entity detection lives under `presidio/recognizers/`, including:

- PAN, Aadhaar, passport, driving license, GSTIN, employee ID
- US phone numbers
- Banking (IFSC, account numbers)
- Infrastructure (IP addresses, hostnames, connection strings)
- Security (API keys, tokens, certificates)

## Architecture Flow

```
Browser Extension
       │
       ▼ POST /api/scan
┌──────────────────────────────────────────────────────┐
│  routes.py (Orchestrator)                            │
│                                                      │
│  1. Presidio ──► detect + mask PII                   │
│  2. Smart Router ──► is_trivial_prompt()?            │
│  3. ECI Classifier ──► LLM Router ──► Provider       │
│     ├── local (Ollama)                               │
│     ├── groq (Groq API)                              │
│     ├── gemini (Google Gemini)                       │
│     └── bedrock (Amazon Bedrock)                     │
│  4. Policy Engine ──► rules.json ──► ALLOW/WARN/BLOCK│
│                                                      │
└──────────────────────────────────────────────────────┘
       │
       ▼ { status, sanitizedPrompt, issues, riskScore }
Browser Extension (shows review modal)
```

## Related Docs

- Root setup guide: [`../README.md`](../README.md)
- Browser extension: [`../browser-extension/README.md`](../browser-extension/README.md)
- Architecture: [`../docs/architecture.md`](../docs/architecture.md)

## Known Limitations

- Local Ollama (phi3:mini on CPU) takes 30-180s per classification — use `strategy=cloud` or `strategy=auto` for demos
- phi3:mini occasionally produces malformed JSON on the 14-field schema — the classifier retries once then falls back to a fail-closed WARN
- Groq/Gemini free tiers have rate limits (30/15 req/min) — sufficient for demo use, not production traffic
- Regex engine is not yet wired into the pipeline
