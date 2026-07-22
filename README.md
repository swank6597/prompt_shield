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
| `presidio/` | PII detection & masking (Microsoft Presidio) | In progress |
| `ollama/` | Local AI risk classification (Ollama + Phi-4-mini) | In progress |
| `chrome-extension/` | Manifest V3 extension for intercepting prompts | Not started |

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

## Current Focus

The active implementation work is in `browser-extension/`. It contains the Manifest V3 extension that:

- Detects supported AI chat pages
- Reads prompt text before send
- Scans prompts through the local API
- Allows `SAFE` prompts
- Blocks `BLOCK` prompts with a warning dialog and bypass flow

## Branch Layout

- `browser-extension-dev` is the main working branch for active development.
- `browser-extension-main` tracks the same project state for the extension branch line.
- `origin/main` exists in the remote history as the older research repo and has been merged into the extension branches so it can be pulled forward later.

## Repository Layout

- [`browser-extension/`](browser-extension/) - Chrome extension source, manifest, icons, and extension README
- `backend/` - planned scanner and policy service implementation
- `knowledge/` - shared research and project knowledge base
- `samples/` - prompt samples and expected outputs
- `tests/` - automated tests
- `docs/` - architecture and project documentation
- `scripts/` - utility scripts

## Extension Docs

See the extension-specific README here:

- [`browser-extension/README.md`](browser-extension/README.md)

## Development Status

- Extension code has been reorganized under `browser-extension/`
- Root repo structure has been created for backend and supporting work
- `origin/main` has been merged into the extension branches so future merges from `main` are possible without losing the extension work

## Notes

- The extension currently falls back to `SAFE` if the local scan API is unavailable, which keeps typing unblocked during development.
- Supported AI sites currently include ChatGPT, Gemini, Claude, DeepSeek, and Microsoft Copilot.
