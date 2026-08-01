# Scripts

Utility and demo scripts. None of these run as part of the served API — they're manual
tools for development and demo prep.

## `presidio_mask_demo.py` — implemented

Interactive CLI for manually testing Presidio PII/secret detection and masking,
including all of `backend/presidio/recognizers/` via `register_all()`. Prints each
detected entity with its score, then the fully masked text.

Run from the repo root with `backend/` on the Python path:

```bash
PYTHONPATH=backend python scripts/presidio_mask_demo.py
```

Type (or paste) multi-line text, then type `END` on its own line to run detection.

## `run_demo.sh` — stub, not implemented

Intended to be a convenience script that starts the backend (and Ollama) and prepares
the environment for a live demo of the Chrome extension. Currently contains only a
header comment describing that intent — no commands yet. Until it's implemented, follow
the manual steps in [`../docs/demo_script.md`](../docs/demo_script.md) or
[`../backend/README.md`](../backend/README.md)'s Quick Start (`start-backend.ps1` /
`start-backend.bat` cover the backend half already).

## `seed_knowledge.py` — stub, not implemented

Intended to validate the Markdown files under `knowledge/` and (re)generate
`knowledge/knowledge_index.json`. Currently contains only a header comment — no
implementation yet. `backend/ai/context_loader.py` doesn't depend on this: it walks
`knowledge/` directly at startup rather than reading an index file, so the backend
works today without this script existing.
