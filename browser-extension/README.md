# PromptShield

PromptShield is a Chrome Extension built with Manifest V3. It detects supported AI chat pages, intercepts prompt sends, scans them through a local API, and shows a review popup before anything is sent to the AI service.

## Project Overview

The extension detects supported AI chat pages, finds the active prompt composer, intercepts send actions, scans the prompt through the local API, and opens a PromptShield review popup when sensitive data is found. The user can then decide whether to send the sanitized prompt, send the original anyway, or cancel.

## Supported Sites

Defined per-site in `content/site-definitions.js` and mirrored in
`manifest.json`'s `host_permissions`/`content_scripts`:

- **ChatGPT** — `chatgpt.com`, `chat.openai.com` (legacy domain)
- **Gemini** — `gemini.google.com`
- **Claude** — `claude.ai`
- **DeepSeek** — `chat.deepseek.com`, `chat.deepseek.ai`
- **Microsoft Copilot** — `copilot.microsoft.com`, `copilot.cloud.microsoft`, and `www.bing.com/chat*` (Bing Chat is matched under this same site definition)
- **Google Search AI** — `www.google.com/search` (AI Overviews follow-ups, AI Mode at `udm=50`)
- **Google Homepage** — `www.google.com` (homepage search bar)

### Navigation-Level Interception

Some surfaces cannot be intercepted via content scripts because the prompt is
embedded in a navigation URL rather than typed into a DOM input:

- **New Tab Page (NTP)** — Chrome's built-in new-tab search box triggers a
  navigation to `google.com/search?q=…`. PromptShield intercepts this via the
  `webNavigation.onBeforeNavigate` API, extracts the query parameter, scans it,
  and redirects to an interstitial review page if sensitive data is detected.
  Anti-double-interception logic ensures the content script on the resulting
  Google Search page does not re-scan the same prompt.

- **Chrome AI (Gemini Nano)** — Monitoring of Chrome's built-in AI features
  (Gemini Nano) is best-effort via the `webRequest` API. Requests to known
  Generative Language API endpoints are observed and logged for audit purposes.
  Due to browser security restrictions, request bodies may not always be
  accessible, so this acts as an alerting mechanism rather than a blocking gate.

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
2. Open DevTools console to see `[PromptShield]` logs.
3. Type a prompt with test sensitive data, for example:
   `My email is john.doe@example.com`
4. Press Enter or click Send.
5. PromptShield should open a popup showing:
   - Detected issues
   - Your original prompt
   - The sanitized prompt
   - Actions: `Cancel`, `Send Original`, `Send Sanitized`

## Current Features

- Manifest V3 extension structure
- Multi-site AI chat detection
- Prompt composer discovery using site-specific adapters, weighted scoring heuristics, and shadow-DOM traversal (`querySelectorAllDeep`) for sites that render the composer inside a shadow root
- Prompt input observation and console logging
- Send button, Enter-key, and form submit interception
- Prompt scan request routed content script → background service worker → `fetch` (the content script never calls the API directly)
- In-page review popup (a shadow-DOM modal injected by `content/modal.js`) with exact detected issues plus an "AI Context Analysis" section (intent, document type, confidence, and risk flags such as secrets/source code/customer data/internal architecture) sourced from the backend's ECI classification
- Client-side fallback in `utils/scan-utils.js` that infers issues from the `reason` string and an original/sanitized diff when the API response omits structured `issues`
- User choice to send sanitized prompt, send original anyway (for `SANITIZE` results), or cancel
- SAFE / SANITIZE / BLOCK response handling — a real `BLOCK` hides the "Send Original" option entirely, so it cannot be overridden
- A separate, static toolbar popup (`popup/popup.html`) showing a feature summary — distinct from the in-page review modal described below; it has no interactivity beyond loading
- Shared logger utility with consistent `[PromptShield]` output
- Chrome New Tab Page search interception via webNavigation API
- Chrome built-in AI (Gemini Nano) best-effort monitoring via webRequest API
- Suggestion chip click interception on Google AI Mode
- Anti-double-interception coordination between NTP and content scripts
- Interstitial review page for navigation-level interception

## Review Popup Flow

When sensitive data is detected:

1. The original send is blocked.
2. PromptShield opens a review modal on the page (injected via `content/modal.js`, not the toolbar popup).
3. The modal shows:
   - Scan status (`SANITIZE` or `BLOCK`)
   - A summary reason
   - Each detected issue with type, matched value, and confidence
   - An "AI Context Analysis" section summarizing the backend's ECI classification (intent, document type, confidence, risk flags), when available
   - The original prompt
   - The sanitized prompt
4. The user chooses:
   - **Cancel** — nothing is sent
   - **Send Sanitized** — the composer is updated with the sanitized prompt and that version is sent (hidden if sanitizing produced no actual change)
   - **Send Original** / **Send Anyway** — only available for `SANITIZE` results; for a `BLOCK` this option is not shown, so the prompt cannot be sent as-is

When no sensitive data is found (`SAFE`), the prompt is sent automatically without opening the modal.

## API Contract

The content script (`content/api-client.js`) never calls `fetch` itself — it
sends a `PROMPTSHIELD_SCAN_PROMPT` message via `chrome.runtime.sendMessage`
to the background service worker (`background/background.js`), which performs
the actual request and returns the (normalized) response. Functionally this
still amounts to:

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
- The extension assumes the scan API is available at `localhost:8081`, but it falls back to SAFE if the API is unavailable (both when `background.js`'s `fetch` throws, and when `api-client.js` gets no response at all) so typing is not blocked during development.
- Port `8080` is commonly occupied on Windows by NVIDIA Broadcast; use `8081` instead.
- Chrome may list extension `console.warn` output under `chrome://extensions` → **Errors**. That page includes intentional warnings, not just failures. Normal scan decisions are logged with `console.log` so they stay out of the Errors list.
- A real `BLOCK` cannot be overridden from the review modal — there is no "Send Original" option in that case, unlike `SANITIZE` results.
- The toolbar popup (`popup/popup.html`) is static/informational only — it does not show scan history, settings, or link to the in-page review modal.
