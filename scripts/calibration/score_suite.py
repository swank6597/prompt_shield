"""Score suite cases exactly the way pre_classify() does, with no LLM calls.

Promoted from the throwaway harness used by plan task 8.1
(scripts/_tmp_score_candidates.py) and kept as the measurement seed for task 8.3.

Fidelity to the production path (backend/ai/pre_classifier.py):
  - Presidio-mask the raw text first; the LEXICAL score is taken on the MASKED
    text, because that is what pre_classify() receives as `masked_text`.
  - The SEMANTIC score is taken on the RAW prompt, because pre_classify() passes
    `prompt` (not `masked_text`) to SemanticEngine.search().
  - hybrid = HYBRID_LEXICAL_WEIGHT * lexical + HYBRID_SEMANTIC_WEIGHT * semantic,
    computed only when the lexical verdict is AMBIGUOUS (tier 2 is not reached
    otherwise).
  - Routing replicates the tier-0/1/2 branch order, including the trivial and
    secrets fast paths that precede any scoring.

Quote convention: the input JSON is expected to hold UNQUOTED prompt text (see
extract_suite.py). Lexical tokenization ignores quotes; the embedding does not.

Threshold overrides let a candidate configuration be evaluated without editing
config.py, so a proposed change can be measured before it is made.

Usage:
    backend/venv/Scripts/python.exe scripts/calibration/score_suite.py \
        [cases.json] [out.json] [--tfidf-public F] [--tfidf-enterprise F] \
        [--k F] [--hybrid-public F] [--hybrid-enterprise F]
"""

import argparse
import json
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_BACKEND = _HERE.parents[1] / "backend"
sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_BACKEND / "ai"))

import config  # noqa: E402
from ai.context_loader import load_knowledge_base  # noqa: E402
from ai.lexical_engine import LexicalEngine, LexicalConfig  # noqa: E402
from ai.semantic_engine import SemanticEngine  # noqa: E402
from presidio.presidio_engine import analyze_text  # noqa: E402
from utils.helpers import is_trivial_prompt  # noqa: E402

# Kept in sync with pre_classifier._SECRET_ENTITY_TYPES.
SECRET_ENTITY_TYPES = {
    "GITHUB_TOKEN", "OPENAI_API_KEY", "AWS_ACCESS_KEY",
    "AWS_SECRET_KEY", "PRIVATE_KEY", "JWT_TOKEN",
}


def parse_args(argv):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("cases", nargs="?", default=str(_HERE / "suite_cases.json"))
    p.add_argument("out", nargs="?", default=str(_HERE / "suite_scores.json"))
    p.add_argument("--tfidf-public", type=float, default=config.TFIDF_PUBLIC_THRESHOLD)
    p.add_argument("--tfidf-enterprise", type=float, default=config.TFIDF_ENTERPRISE_THRESHOLD)
    p.add_argument("--k", type=float, default=config.LEXICAL_SATURATION_K)
    p.add_argument("--hybrid-public", type=float, default=config.HYBRID_PUBLIC_THRESHOLD)
    p.add_argument("--hybrid-enterprise", type=float, default=config.HYBRID_ENTERPRISE_THRESHOLD)
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    docs = load_knowledge_base()
    lex = LexicalEngine(docs, LexicalConfig(
        public_threshold=args.tfidf_public,
        enterprise_threshold=args.tfidf_enterprise,
        saturation_k=args.k,
    ))
    sem = SemanticEngine(docs)
    if not sem.available:
        print("ERROR: SemanticEngine unavailable - tier-2 numbers would be fabricated.",
              file=sys.stderr)
        return 2

    print(f"# K={args.k} tfidf=[{args.tfidf_public}, {args.tfidf_enterprise}) "
          f"hybrid=[{args.hybrid_public}, {args.hybrid_enterprise})", file=sys.stderr)

    cases = json.loads(Path(args.cases).read_text(encoding="utf-8-sig"))

    out = []
    for c in cases:
        text = c["text"]
        pres = analyze_text(text)
        masked = pres["maskedText"]
        lr = lex.score(masked)
        entities = sorted({e["entity_type"] for e in pres["entities"]})

        # Invert raw/(raw+K) to recover the raw TF-IDF mass, so a different K can
        # be applied later without re-tokenizing.
        n = lr.tfidf_score
        raw = (args.k * n / (1.0 - n)) if n < 1.0 else float("inf")

        rec = {
            "id": c["id"],
            "num": c.get("num"),
            "expected": c.get("expected"),
            "source": c.get("source"),
            "human": c.get("human"),
            "type": c.get("type"),
            "text": text,
            "entity_count": pres["entityCount"],
            "entities": entities,
            "lex": lr.tfidf_score,
            "raw": round(raw, 6),
            "verdict": lr.verdict,
            "matched": lr.matched_terms,
            "sem": None,
            "hybrid": None,
            "tier2": False,
            "path": None,
            "needs_llm": None,
        }

        if pres["entityCount"] == 0 and is_trivial_prompt(text):
            rec["path"] = "trivial"
            rec["needs_llm"] = False
        elif set(entities) & SECRET_ENTITY_TYPES:
            rec["path"] = "hard_block"
            rec["needs_llm"] = False
        elif lr.verdict == "PUBLIC":
            rec["path"] = "pii_only" if pres["entityCount"] > 0 else "general_knowledge"
            rec["needs_llm"] = False
        elif lr.verdict == "ENTERPRISE_LIKELY":
            rec["path"] = "enterprise_lexical_needs_review"
            rec["needs_llm"] = True
        else:  # AMBIGUOUS -> tier 2
            sr = sem.search(text)
            hybrid = round(config.HYBRID_LEXICAL_WEIGHT * lr.tfidf_score
                           + config.HYBRID_SEMANTIC_WEIGHT * sr.semantic_score, 6)
            rec["sem"] = sr.semantic_score
            rec["hybrid"] = hybrid
            rec["tier2"] = True
            if hybrid < args.hybrid_public:
                rec["path"] = "semantic_confirmed_public"
                rec["needs_llm"] = False
            elif hybrid >= args.hybrid_enterprise:
                rec["path"] = "enterprise_hybrid_needs_review"
                rec["needs_llm"] = True
            else:
                rec["path"] = "true_ambiguity"
                rec["needs_llm"] = True
        out.append(rec)

    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {len(out)} scored records -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
