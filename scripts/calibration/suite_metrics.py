"""The ONE implementation of the labelled-suite metrics.

Imported by both consumers so they cannot disagree:

  - scripts/calibration/report_metrics.py   the human-readable calibration report
  - tests/test_scoring_regression.py        the standing regression harness

Why this module exists at all: task 8.3 of specs/lexical-semantic-fix asks for a
test that fails when the lexical score stops correlating with the labels. The
obvious way to write that test is to recompute AUC inside the test file. Then
there are two AUC implementations, and the first time one of them changes - a
different tie rule, a different positive class, a different exclusion set - the
report and the test start describing different things while both stay green.
The number the test defends has to be the same number the report prints.

DEFINITIONS, fixed here so both consumers inherit them:

  positive class    expected label "BLOCK".
  negative class    "ALLOW" and "ALLOW / WARN". The latter records a suite
                    tolerance for a WARN outcome; on no reading is it a block.
  AUC               P(random positive scores above random negative), ties at
                    0.5. This is the Mann-Whitney statistic, so it measures
                    RANKING only and is invariant under any strictly increasing
                    transform of the score - including raw/(raw+K), which is why
                    LEXICAL_SATURATION_K cannot move it (see config.py).
  separation gap    min(positive) - max(negative). Must be > 0 for a single
                    threshold to separate the classes cleanly. It can be
                    strongly negative while AUC is high: one outlier sets it.

  lexically scored  every case EXCEPT those decided before any lexical scoring
                    (decision paths "trivial" and "hard_block"). Including them
                    would credit the lexical score with catches Presidio made.

  no-LLM paths      the decision paths that return needs_llm=False. A BLOCK
                    label on one of these is unrecoverable: nothing downstream
                    re-examines the prompt. "hard_block" and "trivial" are the
                    exception - there Presidio's own detection is the evidence
                    and policy blocks without the LLM by design.
"""

from __future__ import annotations

# =============================================================================
# Label / class definitions
# =============================================================================

POSITIVE_LABEL = "BLOCK"

# Decided before any lexical scoring happens, so excluded from lexical metrics.
SECRET_PATHS = frozenset({"hard_block", "trivial"})

# Every decision path that returns needs_llm=False in pre_classifier.pre_classify().
NO_LLM_PATHS = frozenset({
    "trivial",
    "hard_block",
    "pii_only",
    "general_knowledge",
    "semantic_confirmed_public",
})

# The subset of NO_LLM_PATHS where skipping the LLM is intended: Presidio found
# a credential, and the block rests on that detection rather than on a score.
BY_DESIGN_NO_LLM_PATHS = SECRET_PATHS


def is_block(rec) -> bool:
    """True if this case's expected label is the positive class."""
    return rec["expected"] == POSITIVE_LABEL


# =============================================================================
# Statistics
# =============================================================================

def auc(pos, neg):
    """P(random positive > random negative), ties counted as 0.5.

    Returns None when either class is empty, because the quantity is undefined
    rather than zero - callers must not silently read that as a failing score.
    """
    if not pos or not neg:
        return None
    wins = 0.0
    for p in pos:
        for n in neg:
            if p > n:
                wins += 1.0
            elif p == n:
                wins += 0.5
    return wins / (len(pos) * len(neg))


def gap(pos, neg):
    """Separation gap: min(positive) - max(negative). None if a class is empty."""
    if not pos or not neg:
        return None
    return min(pos) - max(neg)


# Spelled-out alias; `gap` is kept because report_metrics.py already reads that way.
separation_gap = gap


def describe(vals):
    """Compact five-number summary of a score distribution."""
    if not vals:
        return "n=0"
    s = sorted(vals)
    n = len(s)
    med = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    return (f"n={n:2d} min={s[0]:.4f} p25={s[max(0, n // 4)]:.4f} med={med:.4f} "
            f"p75={s[min(n - 1, 3 * n // 4)]:.4f} max={s[-1]:.4f}")


# =============================================================================
# Cohort and class selection
# =============================================================================

def lexically_scored(recs):
    """The cases the lexical score is actually responsible for."""
    return [r for r in recs if r["path"] not in SECRET_PATHS]


def split_by_class(recs, key):
    """(positive_scores, negative_scores) for one score key, skipping Nones."""
    scored = [r for r in recs if r.get(key) is not None]
    pos = [r[key] for r in scored if is_block(r)]
    neg = [r[key] for r in scored if not is_block(r)]
    return pos, neg


def auc_and_gap(recs, key):
    """(auc, gap, positives, negatives) for one cohort on one score key."""
    pos, neg = split_by_class(recs, key)
    return auc(pos, neg), gap(pos, neg), pos, neg


def block_cases_skipping_llm(recs):
    """BLOCK-labelled cases that never reach the LLM, as {case id: decision path}.

    This is the set task 8.3 pins. A new entry means a labelled block became
    unrecoverable, which no later layer can undo.
    """
    return {r["id"]: r["path"] for r in recs if is_block(r) and r["path"] in NO_LLM_PATHS}
