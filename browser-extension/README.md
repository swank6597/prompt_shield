# Prompt Guardian

Prompt Guardian is a Chrome Extension built with Manifest V3. It detects supported AI chat pages, intercepts prompt sends, scans them through a local API, and shows a review popup before anything is sent to the AI service.

## Project Overview

The extension detects supported AI chat pages, finds the active prompt composer, intercepts send actions, scans the prompt through the local API, and opens a Prompt Guardian review popup when sensitive data is found. The user can then decide whether to send the sanitized prompt, send the original anyway, or cancel.

## Supported Sites

- ChatGPT
- Gemini
- Claude
- DeepSeek
- Microsoft Copilot

## Quick Start

### 1. Start the backend API

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

Verify the API is running:

`http://localhost:8081/health`

Backend details: [`../backend/README.md`](../backend/README.md)

### 2. Load the extension

1. Open Chrome.
2. Go to `chrome://extensions`.
3. Enable `Developer mode`.
4. Click `Load unpacked`.
5. Select `PromptGuardExtension\browser-extension`.
6. Reload the extension after code changes.

### 3. Test the review popup

1. Open a supported AI chat site.
2. Open DevTools console to see `[Prompt Guardian]` logs.
3. Type a prompt with test sensitive data, for example:
   `My email is john.doe@example.com`
4. Press Enter or click Send.
5. Prompt Guardian should open a popup showing:
   - Detected issues
   - Your original prompt
   - The sanitized prompt
   - Actions: `Cancel`, `Send Original`, `Send Sanitized`

## Current Features

- Manifest V3 extension structure
- Multi-site AI chat detection
- Prompt composer discovery using site-specific adapters and shared heuristics
- Prompt input observation and console logging
- Send button, Enter-key, and form submit interception
- Prompt scan request routed through the background worker
- In-page review popup with exact detected issues
- User choice to send sanitized prompt, send original anyway, or cancel
- SAFE / SANITIZE / BLOCK response handling
- Shared logger utility with consistent `[Prompt Guardian]` output

## Review Popup Flow

When sensitive data is detected:

1. The original send is blocked.
2. Prompt Guardian opens a popup on the page.
3. The popup shows:
   - Scan status (`SANITIZE` or `BLOCK`)
   - A summary reason
   - Each detected issue with type, matched value, and confidence
   - The original prompt
   - The sanitized prompt
4. The user chooses:
   - **Cancel** — nothing is sent
   - **Send Sanitized** — the composer is updated with the sanitized prompt and that version is sent
   - **Send Original** / **Send Anyway** — the original prompt is sent despite the warning

When no sensitive data is found (`SAFE`), the prompt is sent automatically without opening the popup.

## API Contract

The extension posts to:

`POST http://localhost:8081/api/scan`

Request:

```json
{ "prompt": "<captured prompt>" }
```

Expected responses:

```json
{ "status": "SAFE", "sanitizedPrompt": "<original prompt>", "issues": [] }
```

```json
{
  "status": "SANITIZE",
  "sanitizedPrompt": "My email is <EMAIL_ADDRESS>",
  "reason": "Detected 1 sensitive item(s): EMAIL_ADDRESS",
  "issues": [
    {
      "entityType": "EMAIL_ADDRESS",
      "value": "john.doe@example.com",
      "score": 0.95
    }
  ]
}
```

```json
{
  "status": "BLOCK",
  "reason": "PII Detected",
  "issues": []
}
```

## Related Docs

- Backend API setup and contract: [`../backend/README.md`](../backend/README.md)
- Root quick start: [`../README.md`](../README.md)

## Known Limitations

- The prompt heuristics are intentionally generic and may need tuning if any supported site changes its DOM significantly.
- The extension assumes the scan API is available at `localhost:8081`, but it falls back to SAFE if the API is unavailable so typing is not blocked during development.
- Port `8080` is commonly occupied on Windows by NVIDIA Broadcast; use `8081` instead.
- Chrome may list extension `console.warn` output under `chrome://extensions` → **Errors**. That page includes intentional warnings, not just failures. Normal scan decisions are logged with `console.log` so they stay out of the Errors list.
