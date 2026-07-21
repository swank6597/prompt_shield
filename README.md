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
