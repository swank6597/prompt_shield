"""Threshold calibration report for plan task 8.2.

Reports every metric THREE WAYS and never averages them together:

  1. HUMAN     - the 15 human-authored baseline cases. The only labels with
                 human authority.
  2. ALL       - all 76 cases. Larger sample, weaker labels.
  3. GENERATED - the 61 machine-generated cases (#16-#76), UNREVIEWED by any
                 human.

If (1) and (3) disagree about where a threshold belongs, that disagreement is a
finding to report, not noise to smooth over. Any threshold justified only by (3)
is provisional pending human review of the labels.

Positive class = expected label "BLOCK". Negative class = "ALLOW" and
"ALLOW / WARN" (the latter records a suite tolerance, and in neither reading is
it a block).

AUC is P(random positive scores above random negative), ties at 0.5. Separation
gap is min(positive) - max(negative): it must be > 0 for a single threshold to
separate the classes cleanly.

Usage:
    python scripts/calibration/report_metrics.py [suite_scores.json]
"""

import json
import sys
from pathlib import Path

# AUC, separation gap, the positive-class definition and the decision-path sets
# all live in suite_metrics, so tests/test_scoring_regression.py defends exactly
# the numbers this report prints. A second copy of the AUC formula here would
# drift from the one the test asserts against, and both would stay green while
# doing so. Resolvable because Python puts this script's own directory on
# sys.path when it is run as a script.
from suite_metrics import (  # noqa: E402
    NO_LLM_PATHS,
    SECRET_PATHS,
    auc,
    auc_and_gap,
    describe,
    gap,
    is_block,
)

_HERE = Path(__file__).resolve().parent

# The "<- current" markers in the sweep tables come from the live config rather
# than hardcoded numbers, so the tables stay honest after a threshold moves.
# Imported defensively: this script is normally run by the system interpreter,
# which has openpyxl but not necessarily python-dotenv (config.py tolerates that).
try:
    sys.path.insert(0, str(_HERE.parents[1] / "backend"))
    import config as _cfg
    CUR_TFIDF_PUBLIC = _cfg.TFIDF_PUBLIC_THRESHOLD
    CUR_HYBRID_PUBLIC = _cfg.HYBRID_PUBLIC_THRESHOLD
except Exception:  # pragma: no cover - report still readable without the markers
    CUR_TFIDF_PUBLIC = None
    CUR_HYBRID_PUBLIC = None


def _marker(value, current) -> str:
    return "   <- current" if current is not None and abs(value - current) < 1e-9 else ""


def cohort_block(name, recs, key, note=""):
    """Print AUC / gap / distributions for one cohort on one score key."""
    a, g, pos, neg = auc_and_gap(recs, key)
    print(f"  {name:11s} {note}")
    print(f"    expected BLOCK : {describe(pos)}")
    print(f"    expected ALLOW : {describe(neg)}")
    if a is None:
        print("    AUC: n/a (one class empty)")
    else:
        print(f"    AUC = {a:.4f}    separation gap = {g:+.4f}"
              f"{'  SEPARABLE' if g > 0 else '  OVERLAP'}")
    return a, g, pos, neg


def sweep_lexical_public(recs, candidates):
    """Effect of TFIDF_PUBLIC_THRESHOLD.

    Below it, a prompt takes general_knowledge / pii_only and NEVER reaches the
    LLM: a BLOCK-labelled case below the threshold is a miss no later layer can
    recover. Above it, the prompt reaches at least tier 2. hard_block/trivial
    cases are excluded - they are decided before any lexical scoring.
    """
    elig = [r for r in recs if r["path"] not in SECRET_PATHS]
    print(f"    (over {len(elig)} cases that actually reach lexical scoring)")
    print(f"    {'thr':>6s} {'BLOCK skipped (no LLM)':>23s} {'ALLOW skipped':>14s} "
          f"{'reach tier1+':>12s}")
    for t in candidates:
        below = [r for r in elig if r["lex"] < t]
        bblk = [r for r in below if is_block(r)]
        ballow = [r for r in below if not is_block(r)]
        print(f"    {t:6.2f} {len(bblk):23d} {len(ballow):14d} {len(elig) - len(below):12d}"
              f"{_marker(t, CUR_TFIDF_PUBLIC)}")
        if bblk:
            print(f"           missed BLOCK: {[(r['id'], round(r['lex'], 4)) for r in bblk]}")


def sweep_hybrid_public(recs, candidates):
    """Effect of HYBRID_PUBLIC_THRESHOLD.

    semantic_confirmed_public is the ONLY tier-2 branch that skips the LLM, so
    this threshold is the entire decision content of the hybrid pair. Setting it
    to 0.0 removes the branch: every tier-2 case then reaches the LLM.
    """
    t2 = [r for r in recs if r["tier2"]]
    print(f"    (over {len(t2)} cases that reach tier 2)")
    print(f"    {'thr':>6s} {'BLOCK skipped (no LLM)':>23s} {'ALLOW skipped':>14s} "
          f"{'LLM calls in cohort':>19s}")
    base_llm = sum(1 for r in recs if r["path"] not in NO_LLM_PATHS)
    for t in candidates:
        below = [r for r in t2 if r["hybrid"] < t]
        bblk = [r for r in below if is_block(r)]
        ballow = [r for r in below if not is_block(r)]
        # LLM calls at this candidate = the calls made in the scored run, plus
        # back the cases that run skipped, minus the ones this candidate skips.
        cur_skipped = [r for r in t2 if r["path"] == "semantic_confirmed_public"]
        llm = base_llm + len(cur_skipped) - len(below)
        print(f"    {t:6.2f} {len(bblk):23d} {len(ballow):14d} {llm:19d}"
              f"{_marker(t, CUR_HYBRID_PUBLIC)}"
              f"{'   (branch disabled)' if t == 0.0 else ''}")
        if bblk:
            print(f"           missed BLOCK: {[(r['id'], r['hybrid']) for r in bblk]}")


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else _HERE / "suite_scores.json"
    recs = json.loads(path.read_text(encoding="utf-8-sig"))

    human = [r for r in recs if r["human"]]
    gen = [r for r in recs if not r["human"]]
    cohorts = [("HUMAN", human), ("ALL", recs), ("GENERATED", gen)]

    print("=" * 78)
    print("PER-CASE MEASUREMENTS (unquoted prompt text; lexical on Presidio-masked,")
    print("semantic on raw, hybrid = 0.4*lex + 0.6*sem, tier 2 only)")
    print("=" * 78)
    hdr = (f"{'id':5s} {'src':3s} {'expected':12s} {'lex':>7s} {'raw':>8s} "
           f"{'verdict':17s} {'sem':>7s} {'hybrid':>7s} {'LLM':>4s} path")
    print(hdr)
    print("-" * len(hdr))
    for r in sorted(recs, key=lambda x: x["num"]):
        sem = "" if r["sem"] is None else f"{r['sem']:.4f}"
        hyb = "" if r["hybrid"] is None else f"{r['hybrid']:.4f}"
        raw = "inf" if r["raw"] == float("inf") else f"{r['raw']:.3f}"
        print(f"{r['id']:5s} {'HUM' if r['human'] else 'gen':3s} {r['expected']:12s} "
              f"{r['lex']:7.4f} {raw:>8s} {r['verdict']:17s} {sem:>7s} {hyb:>7s} "
              f"{'yes' if r['needs_llm'] else 'NO':>4s} {r['path']}")

    print()
    print("=" * 78)
    print("1. LEXICAL SCORE  (drives TFIDF_PUBLIC_THRESHOLD / TFIDF_ENTERPRISE_THRESHOLD)")
    print("=" * 78)
    print("Secrets/trivial cases excluded: they are decided before lexical scoring,")
    print("so including them would credit the lexical score with catches it did not make.")
    for name, group in cohorts:
        elig = [r for r in group if r["path"] not in SECRET_PATHS]
        cohort_block(name, elig, "lex", f"({len(elig)} of {len(group)} scored)")
    print()
    print("  Including the secrets/trivial cases (for completeness only):")
    for name, group in cohorts:
        cohort_block(name, group, "lex", f"({len(group)} cases)")

    print()
    print("=" * 78)
    print("2. HYBRID SCORE  (drives HYBRID_PUBLIC_THRESHOLD / HYBRID_ENTERPRISE_THRESHOLD)")
    print("=" * 78)
    print("Only defined for tier-2 cases (lexical verdict AMBIGUOUS).")
    for name, group in cohorts:
        t2 = [r for r in group if r["tier2"]]
        cohort_block(name, t2, "hybrid", f"({len(t2)} of {len(group)} reach tier 2)")
    print()
    print("  Semantic component alone, same tier-2 subset:")
    for name, group in cohorts:
        t2 = [r for r in group if r["tier2"]]
        cohort_block(name, t2, "sem", f"({len(t2)} cases)")

    print()
    print("=" * 78)
    print("3. THRESHOLD SWEEPS")
    print("=" * 78)
    lex_cands = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35]
    hyb_cands = [0.0, 0.10, 0.20, 0.25, 0.28, 0.30, 0.35, 0.40]
    for name, group in cohorts:
        print(f"\n  --- TFIDF_PUBLIC_THRESHOLD, {name} cohort ---")
        sweep_lexical_public(group, lex_cands)
    for name, group in cohorts:
        print(f"\n  --- HYBRID_PUBLIC_THRESHOLD, {name} cohort ---")
        sweep_hybrid_public(group, hyb_cands)

    print()
    print("=" * 78)
    print("4. ROUTING / COST")
    print("=" * 78)
    paths = {}
    for r in recs:
        paths.setdefault(r["path"], []).append(r)
    for p in sorted(paths, key=lambda x: -len(paths[x])):
        group = paths[p]
        blk = [r for r in group if is_block(r)]
        flag = "  *** SKIPS LLM ***" if p in NO_LLM_PATHS else ""
        print(f"  {p:34s} n={len(group):3d}  expected-BLOCK={len(blk):2d}{flag}")
    llm = [r for r in recs if r["path"] not in NO_LLM_PATHS]
    print(f"\n  LLM calls: {len(llm)} of {len(recs)} ({len(llm) / len(recs) * 100:.0f}%)")

    print()
    print("=" * 78)
    print("5. BLOCK-LABELLED CASES THAT NEVER REACH THE LLM")
    print("=" * 78)
    print("A BLOCK label on a no-LLM path means no later layer can recover the")
    print("verdict, EXCEPT on hard_block, where Presidio's own detection is the")
    print("evidence and policy blocks without the LLM by design.")
    for r in sorted(recs, key=lambda x: x["num"]):
        if is_block(r) and r["path"] in NO_LLM_PATHS:
            hyb = "n/a" if r["hybrid"] is None else f"{r['hybrid']:.4f}"
            by_design = r["path"] in SECRET_PATHS
            print(f"  {r['id']:5s} {'HUM' if r['human'] else 'gen'} {r['path']:28s} "
                  f"lex={r['lex']:.4f} hybrid={hyb:>7s} "
                  f"{'(blocks by design)' if by_design else '<-- UNRECOVERABLE MISS'}")
            if not by_design:
                print(f"        entities={r['entities']}")
                print(f"        matched_terms={r['matched'][:12]}")
                print(f"        {r['text'][:110]}")

    print()
    print("=" * 78)
    print("6. RAW TF-IDF MASS AND SATURATION K")
    print("=" * 78)
    print("raw/(raw+K) is strictly increasing in raw, so K cannot reorder two prompts")
    print("and cannot change AUC or the separation gap's SIGN. It only relocates the")
    print("thresholds on the curve. Shown: what normalized cut each K needs to keep")
    print("the CURRENT raw-score decision boundaries.")
    elig = [r for r in recs if r["path"] not in SECRET_PATHS and r["raw"] != float("inf")]
    for name, group in cohorts:
        sub = [r for r in elig if r in group]
        pos = [r["raw"] for r in sub if is_block(r)]
        neg = [r["raw"] for r in sub if not is_block(r)]
        print(f"  {name:11s} raw BLOCK: {describe(pos)}")
        print(f"  {'':11s} raw ALLOW: {describe(neg)}")
        a, g = auc(pos, neg), gap(pos, neg)
        if a is not None:
            print(f"  {'':11s} AUC = {a:.4f} (identical to normalized, as it must be), "
                  f"raw gap = {g:+.4f}")
    print()
    for K in [6.0, 9.0, 12.0, 18.0, 24.0]:
        cut_p = 0.15
        raw_at_p = K * cut_p / (1 - cut_p)
        raw_at_e = K * 0.45 / (1 - 0.45)
        print(f"  K={K:5.1f}: current thresholds 0.15/0.45 sit at raw {raw_at_p:6.3f} / "
              f"{raw_at_e:6.3f}")
    print("  To hold the raw boundaries fixed at K=12 (raw 2.118 / 9.818), any other K")
    print("  needs its normalized cuts moved to raw/(raw+K) of those same raw values.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
