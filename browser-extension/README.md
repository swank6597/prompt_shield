# Prompt Guardian

Prompt Guardian is a Chrome Extension built with Manifest V3. It now supports a multi-site AI chat architecture and implements Milestones 2 through 5 in a single modular flow.

## Project Overview

The extension detects supported AI chat pages, finds the active prompt composer, reads prompt text while typing, intercepts send actions, sends the prompt to a local scan API, and either allows or blocks the send based on the response.

## Supported Sites

- ChatGPT
- Gemini
- Claude
- DeepSeek
- Microsoft Copilot

## Installation Steps

1. Open Chrome.
2. Go to `chrome://extensions`.
3. Enable `Developer mode`.
4. Click `Load unpacked`.
5. Select `PromptGuardExtension\browser-extension`.

## How to Load Unpacked Extension

After loading the unpacked folder, open one of the supported AI chat sites listed above.

Open DevTools console to see the Prompt Guardian logs.

## Current Features

- Manifest V3 extension structure
- Multi-site AI chat detection
- Prompt composer discovery using site-specific adapters and shared heuristics
- Prompt input observation and console logging
- Send button and Enter-key interception
- Prompt scan request routed through the background worker
- SAFE / BLOCK response handling
- In-page warning modal for blocked prompts
- One-time `Send Anyway` bypass
- Shared logger utility with consistent `[Prompt Guardian]` output

## Milestones Implemented

- Milestone 2: Detect input box, read prompt, print it to the console
- Milestone 3: Detect send button and Enter key, intercept before send
- Milestone 4: Send prompt to a dummy Spring Boot REST API and log the response
- Milestone 5: Allow SAFE prompts, block BLOCK prompts, and show a warning dialog

## API Contract

The extension posts to:

`POST http://localhost:8080/api/scan`

Request:

```json
{ "prompt": "<captured prompt>" }
```

Expected responses:

```json
{ "status": "SAFE" }
```

or

```json
{ "status": "BLOCK", "reason": "PII Detected" }
```

## Known Limitations

- The prompt heuristics are intentionally generic and may need tuning if any supported site changes its DOM significantly.
- The extension assumes the scan API is available at `localhost:8080`, but it falls back to SAFE if the API is unavailable so typing is not blocked during development.
