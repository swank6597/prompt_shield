# Samples

Scaffolding for a labeled prompt fixture set, intended to drive
[`tests/test_pipeline_e2e.py`](../tests/test_pipeline_e2e.py). **Currently empty** —
each subfolder holds only a `.gitkeep` placeholder.

| Folder | Intended contents |
|---|---|
| `safe_prompts/` | Prompts expected to resolve `ALLOW`/`SAFE` |
| `warning_prompts/` | Prompts expected to resolve `WARN`/`MASK` (`SANITIZE` to the extension) |
| `blocked_prompts/` | Prompts expected to resolve `BLOCK` |
| `expected_results/` | The expected `/api/scan` (or `/analyze`) response for each sample prompt, to diff against in `test_pipeline_e2e.py` |

## Why this matters

`test_pipeline_e2e.py` is currently just a header comment describing its intent (run
every sample through the full pipeline and diff against `expected_results/`) — it has
no fixtures to run against yet, so populating this folder is a prerequisite for
implementing that test.

## Suggested approach

Until a script formalizes this, the prompts already curated in
[`../tests/test_scenarios.md`](../tests/test_scenarios.md) (Sections A, C, and D are
deterministic/exact-match — good candidates) are a reasonable starting set to copy in,
each as its own file plus a matching JSON file under `expected_results/`.
