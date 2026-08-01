"""Extract the labelled test suite from tests/PromptShield_TestSuite.xlsx to JSON.

Why this exists as a separate step: the interpreter that has the scoring engines
(backend/venv) does not have openpyxl, and the interpreter that has openpyxl
(system Python) does not have sentence-transformers/faiss. So extraction and
scoring are two processes communicating through a JSON file.

READ-ONLY with respect to the workbook. Never writes to it.

Quote convention (important, and the source of a real measurement discrepancy):
the Prompt cells wrap the prompt text in straight double quotes for display.
The lexical tokenizer discards them, but the sentence-transformer embedding does
NOT - re-scoring quoted text moves semantic scores by up to ~0.09 and can flip a
decision path. This script strips one layer of wrapping quotes so the scored
text is the prompt a user would actually type. Every number downstream is on
UNQUOTED text.

Usage:
    "C:\\Program Files\\Python314\\python.exe" scripts/calibration/extract_suite.py [out.json]
"""

import json
import sys
from pathlib import Path

import openpyxl

SUITE = Path(__file__).resolve().parents[2] / "tests" / "PromptShield_TestSuite.xlsx"
DEFAULT_OUT = Path(__file__).resolve().parent / "suite_cases.json"

SOURCE_HUMAN = "Human-authored (baseline)"


def strip_display_quotes(text: str) -> str:
    """Remove one layer of wrapping straight double quotes, if present."""
    t = text.strip()
    if len(t) >= 2 and t.startswith('"') and t.endswith('"'):
        t = t[1:-1]
    return t


def main() -> int:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT

    wb = openpyxl.load_workbook(SUITE, read_only=True, data_only=True)
    ws = wb["Sheet1"]

    cases = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        num = row[0]
        if num is None:
            continue
        kind = row[1]
        prompt = row[2]
        expected = row[3]
        why = row[4]
        source = row[5] if len(row) > 5 else None
        if prompt is None:
            continue
        cases.append({
            "id": f"#{num}",
            "num": int(num),
            "type": kind,
            "text": strip_display_quotes(str(prompt)),
            "expected": expected,
            "why": why,
            "source": source,
            "human": source == SOURCE_HUMAN,
        })

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(cases, ensure_ascii=False, indent=1), encoding="utf-8")

    n_human = sum(1 for c in cases if c["human"])
    print(f"extracted {len(cases)} cases -> {out_path}")
    print(f"  human-authored: {n_human}   machine-generated: {len(cases) - n_human}")
    dist = {}
    for c in cases:
        dist[c["expected"]] = dist.get(c["expected"], 0) + 1
    print(f"  expected-label distribution: {dist}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
