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
## `calibration/` — threshold measurement harness

Measures how the lexical, semantic and hybrid scores separate the labelled cases in
`tests/PromptShield_TestSuite.xlsx`, and what each `config.py` threshold does to
routing. Written for task 8.2 of
[`../specs/lexical-semantic-fix/plan.md`](../specs/lexical-semantic-fix/plan.md) and
kept as the seed for task 8.3's standing regression check. Read-only with respect to
the workbook.

It takes **two interpreters**, because neither has everything: `backend/venv` has the
scoring engines but not `openpyxl`, and the system Python has `openpyxl` but not
`sentence-transformers`/`faiss`. The two halves talk through JSON files, which are
git-ignored.

```powershell
# 1. workbook -> JSON  (needs openpyxl)
& "C:\Program Files\Python314\python.exe" scripts/calibration/extract_suite.py

# 2. score every case the way pre_classify() does, no LLM calls  (needs the engines)
& backend\venv\Scripts\python.exe scripts/calibration/score_suite.py

# 3. three-way metrics: human baseline / all labels / machine-generated only
& "C:\Program Files\Python314\python.exe" scripts/calibration/report_metrics.py
```

`score_suite.py` accepts `--tfidf-public`, `--tfidf-enterprise`, `--k`,
`--hybrid-public` and `--hybrid-enterprise`, so a candidate configuration can be
measured before `config.py` is touched. `diff_routing.py` diffs two scored runs by
decision path, which is how a proposed change is shown to move exactly the cases
claimed and no others.

`run_suite_e2e.py` is the only script here that **makes real LLM calls**. It replicates
`routes.py::scan_prompt()` stage for stage, minus API-key auth and the audit-log write,
and defaults to the 15 human-authored baseline cases. Mind the provider rate limit; it
sleeps between calls.

Prompt-text convention: the workbook wraps prompts in display quotes. `extract_suite.py`
strips them, because the TF-IDF tokenizer ignores quotes but the sentence-transformer
embedding does not — quoted text shifts semantic scores by up to ~0.09 and can flip a
decision path. Every number these scripts report is on unquoted text.
