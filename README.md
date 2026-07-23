# PromptShield AI — Research Repo

Research and prototyping space for **PromptShield AI**, our AI Hackathon 2026 project
(Theme: preventing sensitive data leakage into external AI models).

This repo is for exploration only — not the final hackathon submission.
Once each piece works independently, we'll pull the working parts into the actual project repo.

## Team
- Gaurav Agrawal — Team Captain / Technical Architect
- Sahil Wankhede — Software Engineer
- Atharva Ajay Gulhane — Software Engineer
- Ranjitsinh Sureshrao Jagtap — Business Analyst
- Mentor: Swapnil Deshmukh

## What we're researching

| Folder | Purpose | Status |
|---|---|---|
| `backend/` | Prompt scanning API (Presidio + `/api/scan`) | In progress |
| `browser-extension/` | Manifest V3 extension for intercepting prompts | In progress |
| `ollama/` | Local AI risk classification (Ollama + Phi-4-mini) | In progress |

## Setup notes

- Python: 3.11 recommended (Presidio has compatibility issues on 3.12.7+)
- .NET: 10 SDK
- Ollama: pull `phi4-mini` model — see `ollama/` for notes

## How to use this repo

Each folder should have its own short notes on:
- What was tried
- What worked / didn't
- Any setup steps needed to reproduce it

Findings and blockers can go in `docs/`.

## Quick Start

Run the backend scanner and load the Chrome extension.

### 1. Start the backend API

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
- Verify the API is running: `http://localhost:8081/health`

### 2. Load the Chrome extension

1. Open `chrome://extensions`
2. Enable **Developer mode**
3. Click **Load unpacked**
4. Select the `browser-extension` folder
5. Reload the extension after code changes

### 3. Test on a supported AI chat site

Open ChatGPT, Gemini, Claude, DeepSeek, or Microsoft Copilot, then send a prompt containing test data such as an email address or phone number. Prompt Guardian should intercept the send and open the review popup.

## Current Focus

The active implementation work is in `browser-extension/`. It contains the Manifest V3 extension that:

- Detects supported AI chat pages
- Reads prompt text before send
- Scans prompts through the local API
- Shows a review popup with detected issues before sending
- Lets the user send the sanitized prompt, send the original anyway, or cancel

## Branch Layout

- `browser-extension-dev` is the main working branch for active development.
- `browser-extension-main` tracks the same project state for the extension branch line.
- `origin/main` exists in the remote history as the older research repo and has been merged into the extension branches so it can be pulled forward later.

## Repository Layout

- [`backend/`](backend/) - FastAPI scanner service, Presidio integration, and backend README
- [`browser-extension/`](browser-extension/) - Chrome extension source, manifest, icons, and extension README
- `knowledge/` - shared research and project knowledge base
- `samples/` - prompt samples and expected outputs
- `tests/` - automated tests
- `docs/` - architecture and project documentation
- `scripts/` - utility scripts

## Docs

- Backend API: [`backend/README.md`](backend/README.md)
- Browser extension: [`browser-extension/README.md`](browser-extension/README.md)

## Development Status

- Extension code has been reorganized under `browser-extension/`
- Root repo structure has been created for backend and supporting work
- `origin/main` has been merged into the extension branches so future merges from `main` are possible without losing the extension work

## Notes

- The extension currently falls back to `SAFE` if the local scan API is unavailable, which keeps typing unblocked during development.
- The scan API runs on `http://localhost:8081` by default.
- Supported AI sites currently include ChatGPT, Gemini, Claude, DeepSeek, and Microsoft Copilot.
