# PromptShield Detection API

FastAPI backend for Prompt Guardian. It scans user prompts for sensitive data using Microsoft Presidio, returns structured issue details, and produces a sanitized version of the prompt for the browser extension.

## Overview

The backend currently runs a Presidio-based detection pipeline:

1. Accept a prompt from the extension
2. Detect PII and custom enterprise entities
3. Mask detected values
4. Return `SAFE`, `SANITIZE`, or `BLOCK` with issue details

Future layers (regex, Ollama classification, policy engine) will plug into this service.

## Requirements

- Python 3.11 recommended (Presidio has compatibility issues on 3.12.7+)
- pip

## Setup

From the repo root:

**Windows (PowerShell):**
```powershell
cd backend
pip install -r requirements.txt
python -m spacy download en_core_web_lg
uvicorn app:app --reload --port 8081
```

**macOS / Linux (bash):**
```bash
cd backend
pip install -r requirements.txt
python -m spacy download en_core_web_lg
uvicorn app:app --reload --port 8081
```

Notes:
- Use port `8081` by default. Port `8080` is often already used on Windows by NVIDIA Broadcast.
- Health check: `http://localhost:8081/health`

## Endpoints

### `GET /health`

Returns service status.

### `POST /analyze`

Presidio analysis endpoint used for direct testing and future tooling.

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

Primary endpoint used by the Prompt Guardian browser extension.

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
    {
      "entityType": "EMAIL_ADDRESS",
      "value": "john.doe@example.com",
      "score": 1.0
    },
    {
      "entityType": "PHONE_NUMBER",
      "value": "555-123-4567",
      "score": 0.85
    }
  ]
}
```

Response when no sensitive data is found:
```json
{
  "status": "SAFE",
  "sanitizedPrompt": "Hello world",
  "issues": []
}
```

## Status Values

| Status | Meaning |
|---|---|
| `SAFE` | No sensitive entities detected |
| `SANITIZE` | Sensitive data detected; sanitized prompt provided |
| `BLOCK` | Reserved for future policy-based hard blocks |

## Project Structure

```
backend/
├── app.py                 # FastAPI entrypoint
├── routes.py              # HTTP routes
├── models.py              # Request/response models
├── requirements.txt       # Python dependencies
├── presidio/              # Presidio analyzer + custom recognizers
├── policy/                # Planned policy engine
├── regex/                 # Planned regex layer
└── ai/                    # Planned semantic classifier
```

## Custom Recognizers

Custom entity detection lives under `presidio/recognizers/`, including:

- PAN, Aadhaar, passport, driving license, GSTIN, employee ID
- US phone numbers
- Additional enterprise/security recognizers

## Related Docs

- Root setup guide: [`../README.md`](../README.md)
- Browser extension docs: [`../browser-extension/README.md`](../browser-extension/README.md)

## Known Limitations

- Detection quality depends on Presidio models and custom recognizer coverage
- Some phone/email formats may not be detected until recognizers are tuned
- Policy engine and semantic classification are not wired in yet
