# test_scoring_regression.py
# Feature: lexical-semantic-fix, task 8.3 (Finding 1)
#
# =============================================================================
# WHY THIS FILE EXISTS
# =============================================================================
# The defect that opened specs/lexical-semantic-fix was a lexical scorer with
# AUC 0.238 - not merely uninformative but ANTI-correlated with the labels:
# prompts expected to be allowed ranked systematically ABOVE prompts expected to
# be blocked, so no threshold could separate them. It shipped, and it passed a
# fully green test suite for as long as it existed.
#
# It passed because every existing test checks the scorer against ITSELF:
#
#   test_lexical_engine.py       Property 1  IDF equals log(N/df) with dampening
#                                Property 2  score stays inside [0.0, 1.0]
#                                Property 3  verdict matches the thresholds
#   test_pre_classifier_routing  Property 6  each verdict routes to its path
#   test_hybrid_scoring.py                   hybrid arithmetic and weights
#
# Every one of those still holds when the score is inverted. Bounds, formulas
# and threshold logic are all internal consistency; none of them mentions the
# intended OUTCOME. Nothing in tests/ asserted that a higher score means a
# prompt more likely to deserve blocking. That is the gap this file closes.
#
# The assertions here are therefore deliberately of a different kind: they
# compare the score against the labelled suite, and they fail when the score
# stops agreeing with it. Concretely, `test_lexical_score_points_the_right_way`
# fails at AUC 0.238 with roughly a 0.36 margin to spare, and the mutation check
# recorded at the bottom of this file confirms that against the actual pre-fix
# code rather than by argument.
#
# =============================================================================
# WHAT IS MEASURED, AND UNDER WHAT CONFIG
# =============================================================================
# Every number below was measured on 2026-08-01 by running this file against the
# real 48-document knowledge corpus and the 76-case labelled suite, through the
# real pre_classify(), with no LLM calls (scoring and routing need none).
#
# Config in force at measurement (backend/config.py defaults, no env overrides):
#
#   TFIDF_PUBLIC_THRESHOLD      = 0.15
#   TFIDF_ENTERPRISE_THRESHOLD  = 0.45
#   LEXICAL_SATURATION_K        = 12.0
#   HYBRID_PUBLIC_THRESHOLD     = 0.0     (semantic_confirmed_public disabled)
#   HYBRID_ENTERPRISE_THRESHOLD = 0.55
#
# Lexical score, expected-BLOCK as the positive class, the 5 secrets cases
# excluded because hard_block decides them before any lexical scoring runs:
#
#                        n      AUC    separation gap
#   human baseline      10   1.0000       +0.0034
#   all labels          71   0.8021       -0.5761
#   generated only      61   0.8097       -0.5761
#
# Routing: 68 of 76 cases reach the LLM. 6 of the 39 BLOCK-labelled cases do
# not - 5 by design via hard_block, plus #68. See KNOWN_BLOCK_LABELLED_LLM_SKIPS.
#
# Read the separation gap with care. It is min(BLOCK) - max(ALLOW), so a single
# outlier sets it: #68 scores 0.0000 and drags it to -0.5761 no matter how well
# the other 70 cases rank. AUC is the ranking measure and the one to defend.
#
# The full report these came from: scripts/calibration/report_metrics.py.
#
# =============================================================================
# FAST vs SLOW: why this whole file runs on every `pytest tests/`
# =============================================================================
# The concern was that scoring 76 cases needs Presidio (spaCy en_core_web_lg,
# ~9 s) and the semantic tier (torch + MiniLM + FAISS, ~4 s), which is too much
# to pay per test run. Measured, it is not, because the suite already pays it:
# tests/test_presidio_product_allowlist.py imports presidio_engine, and
# tests/test_integration_routing.py imports ai.pre_classifier, whose module-level
# init constructs both engines. Both are in sys.modules by the time this file
# runs, so the marginal cost here is only the per-case work:
#
#   76 Presidio analyses, 76 lexical scorings, and the ~38 semantic searches for
#   the cases that reach tier 2 - all of it inside one session-scoped fixture.
#
# Measured with `pytest --durations`: 0.95 s of fixture setup, and not one of the
# 10 test bodies is slow enough to appear in the slowest twelve. Whole-suite
# effect: 136 passed in 54.2 s / 58.7 s without this file, 146 passed in 55.2 s /
# 56.1 s with it - the roughly 1 s of added work is smaller than the suite's own
# run-to-run variance. Run on its own the file takes ~13.5 s, almost all of it
# the cold Presidio (9 s) and semantic (4 s) loads it would otherwise share.
#
# The engines are NOT reconstructed here. The lexical score comes from
# pre_classifier's own instance - the one pre_classify() routes on - so there is
# no second index to fall out of step with the first.
#
# The alternatives were considered and rejected. Marking it slow and opt-in
# means the AUC inversion - the entire defect class - is not checked by default,
# which is how the defect survived in the first place. Committing pre-scored
# output as a fixture and asserting against that checks the fixture, not the
# scorer: the numbers would stay green with the engine deleted. So the scores are
# recomputed live, from the real corpus, every run.
#
# One input IS read from a committed extract: the labelled cases, via
# scripts/calibration/suite_cases.json, because openpyxl is not installed in
# backend/venv and this interpreter cannot open the .xlsx.
# test_labelled_suite_extract_matches_the_workbook pins the workbook's hash so
# the extract cannot silently go stale against it.
#
# =============================================================================
# NON-VACUITY
# =============================================================================
# tests/conftest.py's small_faiss_index fixture wraps pytest.importorskip in a
# try/except and yields None on failure, which task 3.2 found means the suite
# passes identically whether the semantic tier is live or dead. Nothing in this
# file repeats that. If the suite extract is missing, if either engine is
# unavailable, or if zero cases load, the tests here FAIL or ERROR - see
# test_measurement_preconditions_hold, which asserts those preconditions
# explicitly rather than degrading around them.

import hashlib
import json
import os
import sys

import pytest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.normpath(os.path.join(_TESTS_DIR, ".."))
_BACKEND_DIR = os.path.join(_REPO_ROOT, "backend")
_CALIBRATION_DIR = os.path.join(_REPO_ROOT, "scripts", "calibration")
for _d in (_BACKEND_DIR, os.path.join(_BACKEND_DIR, "ai"), _CALIBRATION_DIR):
    if _d not in sys.path:
        sys.path.insert(0, _d)

import config  # noqa: E402
import ai.pre_classifier as pre_classifier  # noqa: E402
from presidio.presidio_engine import analyze_text  # noqa: E402

# AUC and the separation gap are NOT reimplemented here. They come from the same
# module scripts/calibration/report_metrics.py uses, so the number this file
# defends is by construction the number that report prints. A private copy would
# drift - a different tie rule or a different exclusion set - and the report and
# the test would then describe different things while both stayed green.
from suite_metrics import (  # noqa: E402
    BY_DESIGN_NO_LLM_PATHS,
    NO_LLM_PATHS,
    auc,
    block_cases_skipping_llm,
    describe,
    gap,
    is_block,
    lexically_scored,
)

SUITE_CASES_JSON = os.path.join(_CALIBRATION_DIR, "suite_cases.json")
WORKBOOK = os.path.join(_TESTS_DIR, "PromptShield_TestSuite.xlsx")


# =============================================================================
# Recorded measurements and the floors derived from them
# =============================================================================
# Measured 2026-08-01 under the config listed at the top of this file.
MEASURED = {
    #                 n    AUC     separation gap
    "human": (10, 1.0000, +0.0034),
    "all": (71, 0.8021, -0.5761),
    "generated": (61, 0.8097, -0.5761),
}

# --- How much can a legitimate change move these? -------------------------
# Measured, not guessed. Leave-one-document-out over all 48 knowledge documents
# (rebuild the index without each document in turn, rescore all 76 cases):
#
#   cohort   base      min over 48 folds   worst fold
#   ALL      0.8021    0.7738  (-0.0283)   token-vault.md
#   HUMAN    1.0000    0.9524  (-0.0476)   data-classification.md
#   GEN      0.8097    0.7801  (-0.0296)   token-vault.md
#
# And under corpus edits far larger than anyone makes by accident:
#
#   drop the 5 largest documents  (43 left)   ALL 0.8156   HUMAN 1.0000
#   drop the 10 largest           (38 left)   ALL 0.8180   HUMAN 1.0000
#   drop the 20 largest           (28 left)   ALL 0.7667   HUMAN 1.0000
#   keep ONLY the 10 largest      (10 left)   ALL 0.6685   HUMAN 0.9762
#
# The lexical score involves no embeddings and no sampling - it is
# raw/(raw+K) over an integer term count - so it is bit-for-bit deterministic
# and contributes no run-to-run variance at all. Embedding nondeterminism can
# only touch the hybrid score, which these AUC floors do not measure.

# ALL cohort floor. Measured 0.8021, worst single-document fold 0.7738, and
# 0.7667 after deleting 42% of the corpus. 0.70 sits below every one of those
# and still leaves +0.20 over the 0.5 coin-flip line. Only the deliberate
# 79%-corpus-deletion scenario (0.6685) breaches it, and at that point the
# corpus has been replaced rather than edited and these numbers need remeasuring
# anyway. Failing here means the score's RANKING has degraded materially: treat
# it as a defect first and a remeasurement second.
AUC_FLOOR_ALL = 0.70

# HUMAN cohort floor, deliberately stricter, because these 15 are the only
# labels with human authority. Measured 1.0000 over 3 BLOCK x 7 ALLOW = 21
# pairs, so the AUC quantum here is 1/21 = 0.0476 and the floor is best read as
# a pair count: 0.90 permits 2 of the 21 pairs to invert (19/21 = 0.9048 passes,
# 18/21 = 0.8571 fails). It can be stricter than the ALL floor because this
# cohort is empirically the more robust of the two - across all 48
# leave-one-document-out folds it never dropped below 0.9524, and it held at
# 1.0000 through deleting the 20 largest corpus documents - so 0.90 leaves twice
# the headroom of the worst measured perturbation. It is NOT set at 1.0000
# because the underlying margin is only +0.0034 (#4 at 0.5542 over #15 at
# 0.5508, about 0.6%), and a knife-edge floor goes red on ordinary edits until
# everyone learns to ignore it.
AUC_FLOOR_HUMAN = 0.90

# The direction floor, asserted separately from the two above and applied to
# both cohorts. AUC_FLOOR_* record where the score IS and may legitimately be
# re-recorded downward if a measured, justified change moves them.
# DIRECTION_FLOOR records what the score must never stop DOING: rank
# expected-BLOCK above expected-ALLOW materially better than chance. Do not
# lower it. 0.60 clears chance by +0.10, sits below every perturbation measured
# above including the 79%-deletion case, and is 2.5x the 0.238 the plan opened
# with.
DIRECTION_FLOOR = 0.60

# The AUC of the original defect, kept as a literal so the tests can state what
# they would have caught (plan Finding 1).
DEFECT_AUC = 0.238

# --- The pinned set: BLOCK-labelled cases that never reach the LLM ---------
# THE HIGHEST-VALUE ASSERTION IN THIS FILE. A BLOCK label on a no-LLM decision
# path is unrecoverable - nothing downstream re-examines the prompt, so there is
# no layer left to catch a mistake. Task 8.2 established this set as exactly 6 of
# the 39 BLOCK-labelled cases, and it is pinned so that a config or code change
# which adds a seventh fails and names it.
#
#   #1 #2 #3 #6 #7   hard_block         BY DESIGN. Presidio detected a
#                                       credential; that detection IS the
#                                       evidence and policy blocks on it without
#                                       needing the LLM's opinion.
#   #68              general_knowledge  A COVERAGE LIMIT, recorded not fixed by
#                                       task 8.2. "Sell a copy of our customer
#                                       list to a lead-generation firm." scores
#                                       lexical 0.0000: it matches no corpus term
#                                       at all, and Presidio finds no entity in
#                                       it. No positive value of
#                                       TFIDF_PUBLIC_THRESHOLD can reach a score
#                                       of exactly zero, so this is not a
#                                       calibration failure - retrieval-based
#                                       scoring simply cannot see a prompt that
#                                       shares no vocabulary with the corpus.
#                                       Only the LLM or an intent rule could
#                                       catch it, and today neither sees it.
KNOWN_BLOCK_LABELLED_LLM_SKIPS = {
    "#1": "hard_block",
    "#2": "hard_block",
    "#3": "hard_block",
    "#6": "hard_block",
    "#7": "hard_block",
    "#68": "general_knowledge",
}

# Composition of the labelled suite as of task 8.1. Pinned so that a change to
# the suite shows up as an explicit composition failure rather than as an
# unexplained shift in the AUC figures above.
EXPECTED_CASE_COUNT = 76
EXPECTED_HUMAN_COUNT = 15
EXPECTED_LABEL_DISTRIBUTION = {"BLOCK": 39, "ALLOW": 27, "ALLOW / WARN": 10}

# sha256 of tests/PromptShield_TestSuite.xlsx as extracted into
# scripts/calibration/suite_cases.json. See
# test_labelled_suite_extract_matches_the_workbook for what to do when it moves.
WORKBOOK_SHA256 = "de20be48828e3d96e08cd775ba04c45c0efd35bf03fa3f63d001ff943ffc6885"

# Kept in sync with pre_classifier._SECRET_ENTITY_TYPES. Only used to explain a
# failure, never to make a routing decision - pre_classify() does that.
SECRET_ENTITY_TYPES = {
    "GITHUB_TOKEN", "OPENAI_API_KEY", "AWS_ACCESS_KEY",
    "AWS_SECRET_KEY", "PRIVATE_KEY", "JWT_TOKEN",
}


# =============================================================================
# Scoring the suite through the live pipeline
# =============================================================================

def load_labelled_cases():
    """The 76 labelled cases, as extracted from the workbook by extract_suite.py.

    No try/except: a missing or malformed extract must raise and error the test
    out, not degrade into a vacuous pass over zero cases.
    """
    with open(SUITE_CASES_JSON, encoding="utf-8-sig") as fh:
        return json.load(fh)


def build_scored_suite(lexical_engine=None):
    """Score and route every labelled case through the REAL pipeline.

    Routing is not reimplemented here - pre_classify() is called directly, so
    the tiering, the branch order and the thresholds are whatever production
    does today and cannot drift from it. No LLM is called: pre_classify()
    returns a routing decision, and that decision is the whole subject of these
    tests.

    The lexical score is recomputed on the Presidio-MASKED text, because that is
    the text pre_classify() hands the lexical engine (it passes the raw prompt to
    the semantic engine instead - the two tiers genuinely see different strings).
    Scoring the raw prompt here would silently measure something the router never
    saw; the equality check in test_measurement_preconditions_hold catches that.

    lexical_engine defaults to the production instance pre_classify() itself
    uses. It is a parameter so a mutation check can substitute a deliberately
    broken engine and confirm these tests actually go red.
    """
    engine = lexical_engine or pre_classifier._lexical_engine_instance

    scored = []
    for case in load_labelled_cases():
        text = case["text"]
        presidio_result = analyze_text(text)
        pre = pre_classifier.pre_classify(text, presidio_result["maskedText"], presidio_result)
        lexical_result = engine.score(presidio_result["maskedText"])

        scored.append({
            "id": case["id"],
            "num": case["num"],
            "expected": case["expected"],
            "human": case["human"],
            "text": text,
            "lex": lexical_result.tfidf_score,
            "verdict": lexical_result.verdict,
            "matched": lexical_result.matched_terms,
            "entity_count": presidio_result["entityCount"],
            "entities": sorted({e["entity_type"] for e in presidio_result["entities"]}),
            # Straight from pre_classify(), never inferred.
            "path": pre["decision_path"],
            "needs_llm": pre["needs_llm"],
            "hybrid": pre["hybrid_score"],
            "sem": (pre["semantic_result"] or {}).get("semantic_score"),
            "tier2": pre["semantic_result"] is not None,
            "routed_lex": (pre["lexical_result"] or {}).get("tfidf_score"),
        })
    return scored


@pytest.fixture(scope="session")
def scored_suite():
    """Session-scoped: the 76-case scoring run happens once for the whole file."""
    return build_scored_suite()


def _cohort(scored, which):
    """The lexically-scored cases of one cohort.

    Cases decided before lexical scoring (hard_block, trivial) are excluded:
    including them would credit the lexical score with catches Presidio made.
    """
    rows = lexically_scored(scored)
    if which == "human":
        return [r for r in rows if r["human"]]
    if which == "generated":
        return [r for r in rows if not r["human"]]
    return rows


def _auc_for(scored, which):
    rows = _cohort(scored, which)
    pos = [r["lex"] for r in rows if is_block(r)]
    neg = [r["lex"] for r in rows if not is_block(r)]
    return auc(pos, neg), gap(pos, neg), pos, neg


def _cohort_report(scored, which):
    """Human-readable evidence, attached to every AUC failure message."""
    a, g, pos, neg = _auc_for(scored, which)
    n, rec_auc, rec_gap = MEASURED[which]
    return (
        f"cohort={which}  n={len(pos) + len(neg)} (recorded {n})\n"
        f"  expected BLOCK : {describe(pos)}\n"
        f"  expected ALLOW : {describe(neg)}\n"
        f"  AUC = {a if a is None else round(a, 4)}   "
        f"separation gap = {'n/a' if g is None else round(g, 4)}\n"
        f"  recorded 2026-08-01: AUC = {rec_auc:.4f}   gap = {rec_gap:+.4f}\n"
        f"  live config: TFIDF_PUBLIC={config.TFIDF_PUBLIC_THRESHOLD} "
        f"TFIDF_ENTERPRISE={config.TFIDF_ENTERPRISE_THRESHOLD} "
        f"K={config.LEXICAL_SATURATION_K} "
        f"HYBRID_PUBLIC={config.HYBRID_PUBLIC_THRESHOLD} "
        f"HYBRID_ENTERPRISE={config.HYBRID_ENTERPRISE_THRESHOLD}\n"
        f"  reproduce: scripts/calibration/score_suite.py then report_metrics.py"
    )


# =============================================================================
# Preconditions. These exist so nothing below can pass vacuously.
# =============================================================================

def test_measurement_preconditions_hold(scored_suite):
    """Everything the measurements below depend on, asserted rather than assumed.

    Each of these, left unchecked, is a way for the rest of this file to report
    success while measuring nothing:

      - zero cases loaded          -> AUC over an empty class, silently skipped
      - lexical engine unavailable -> pre_classify returns engine_degraded for
                                      everything and no score is ever computed
      - semantic tier dead         -> AMBIGUOUS degrades straight to the LLM, so
                                      tier 2 is never exercised and the routing
                                      assertion covers two tiers instead of three
                                      (this is exactly the hole task 3.2 found in
                                      conftest.py's small_faiss_index fixture)
      - index empty                -> every score is 0.0 and AUC is a tie at 0.5
      - harness scoring the wrong  -> AUC measured on text the router never saw
        string
    """
    assert len(scored_suite) == EXPECTED_CASE_COUNT, (
        f"loaded {len(scored_suite)} cases, expected {EXPECTED_CASE_COUNT}. "
        f"If the workbook grew, re-run scripts/calibration/extract_suite.py, "
        f"re-measure, and update the recorded figures in this file."
    )

    assert pre_classifier._lexical_available is True, (
        "LexicalEngine is unavailable, so pre_classify() degrades every prompt "
        "to the LLM and there is no lexical score to measure."
    )
    engine = pre_classifier._lexical_engine_instance
    assert engine is not None and engine.num_docs > 0, (
        "LexicalEngine has an empty corpus; every score would be 0.0 and the AUC "
        "would be a meaningless tie."
    )
    assert engine.inverted_index, "inverted index is empty"

    assert pre_classifier._semantic_available is True, (
        "SemanticEngine is unavailable. Tier 2 never runs, so the routing "
        "assertions below would cover a two-tier pipeline while production runs "
        "three. Install sentence-transformers and faiss-cpu (plan task 3.1) - "
        "do NOT skip this test."
    )

    # The tiers must actually have been exercised, not merely importable.
    nonzero = [r for r in scored_suite if r["lex"] > 0.0]
    assert len(nonzero) >= EXPECTED_CASE_COUNT // 2, (
        f"only {len(nonzero)} of {len(scored_suite)} cases scored above 0.0; "
        f"the index is probably not being matched at all"
    )
    tier2 = [r for r in scored_suite if r["tier2"]]
    assert tier2, (
        "no case reached tier 2, so the semantic tier contributed nothing to "
        "this run even though it reports itself available"
    )
    assert any(r["sem"] is not None and r["sem"] > 0.0 for r in tier2), (
        "tier 2 ran but produced no nonzero semantic score - the FAISS index is "
        "likely empty"
    )

    # The harness must be scoring the same string the router scored. This is the
    # check that catches a harness measuring the raw prompt while pre_classify()
    # scored the Presidio-masked text (score_suite.py's docstring records that
    # the two diverge, and that quoting alone moved semantic scores by ~0.09).
    for r in scored_suite:
        if r["routed_lex"] is not None:
            assert r["lex"] == pytest.approx(r["routed_lex"], abs=1e-9), (
                f"{r['id']}: harness scored {r['lex']} but pre_classify() routed on "
                f"{r['routed_lex']}. The harness is measuring a different input than "
                f"production - the AUC below would not describe the deployed scorer."
            )


def test_labelled_suite_composition_is_unchanged(scored_suite):
    """Pin the suite's shape, so a label change cannot quietly move the metrics.

    61 of the 76 labels are machine-generated and UNREVIEWED (task 8.1). The
    recorded AUC figures are only meaningful against the specific set of labels
    they were measured on, so a change in composition has to surface here as its
    own failure rather than as a puzzling drift in AUC.
    """
    human = [r for r in scored_suite if r["human"]]
    assert len(human) == EXPECTED_HUMAN_COUNT, (
        f"human-authored cohort is {len(human)}, expected {EXPECTED_HUMAN_COUNT}"
    )

    distribution = {}
    for r in scored_suite:
        distribution[r["expected"]] = distribution.get(r["expected"], 0) + 1
    assert distribution == EXPECTED_LABEL_DISTRIBUTION, (
        f"expected-label distribution is {distribution}, recorded "
        f"{EXPECTED_LABEL_DISTRIBUTION}. Re-measure the figures in this file "
        f"before updating this pin."
    )


def test_labelled_suite_extract_matches_the_workbook():
    """The committed extract must correspond to the workbook it came from.

    This file reads scripts/calibration/suite_cases.json rather than the .xlsx,
    because openpyxl is not installed in backend/venv. That indirection has one
    failure mode: someone edits the workbook, the extract stays behind, and every
    metric here is then measured against labels nobody has. Hashing the workbook
    closes it without needing openpyxl.

    If this fails, the LABELS CHANGED. Re-run:
        "C:/Program Files/Python314/python.exe" scripts/calibration/extract_suite.py
        backend/venv/Scripts/python.exe scripts/calibration/score_suite.py
        backend/venv/Scripts/python.exe scripts/calibration/report_metrics.py
    then update WORKBOOK_SHA256, the composition pins, the recorded AUC figures
    and KNOWN_BLOCK_LABELLED_LLM_SKIPS from the new report. Do not update the
    hash alone: that would re-point the pin without re-measuring anything.
    """
    with open(WORKBOOK, "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    assert digest == WORKBOOK_SHA256, (
        f"tests/PromptShield_TestSuite.xlsx has changed.\n"
        f"  expected sha256 {WORKBOOK_SHA256}\n"
        f"  actual   sha256 {digest}\n"
        f"The recorded metrics in this file were measured against the previous "
        f"contents and no longer describe the suite. See this test's docstring."
    )


# =============================================================================
# 1 + 2. The score must correlate with the labels, and in the right direction
# =============================================================================

def test_lexical_score_points_the_right_way(scored_suite):
    """DIRECTION. The assertion the 0.238 defect would have failed.

    AUC is P(a randomly chosen expected-BLOCK prompt scores above a randomly
    chosen expected-ALLOW prompt). 0.5 is a coin flip; below 0.5 the score is
    actively inverted, which is what shipped: AUC 0.238 over the human baseline
    cases, meaning an expected-ALLOW prompt outranked an expected-BLOCK prompt
    about three times in four.

    At 0.238 this assertion fails on both cohorts by a margin of ~0.36. That is
    the entire point of the file, so it is asserted on its own rather than left
    implied by the tighter floors in the next two tests: those record where the
    score currently is and may be re-recorded after a measured change, whereas
    this one records what the score must never stop doing.
    """
    for which in ("all", "human"):
        a, _, pos, neg = _auc_for(scored_suite, which)
        assert a is not None, f"AUC undefined for the {which} cohort: one class is empty"
        assert a > DIRECTION_FLOOR, (
            f"The lexical score no longer ranks expected-BLOCK above "
            f"expected-ALLOW materially better than chance.\n"
            f"  AUC = {a:.4f}, required > {DIRECTION_FLOOR} "
            f"(0.5 = coin flip, < 0.5 = inverted)\n"
            f"  For reference, the defect this harness exists to catch measured "
            f"{DEFECT_AUC}.\n"
            f"{_cohort_report(scored_suite, which)}"
        )


def test_lexical_auc_floor_all_labels(scored_suite):
    """FLOOR, full suite. Recorded 0.8021 over 71 lexically-scored cases.

    Floor 0.70. Justification is in the AUC_FLOOR_ALL comment: measured
    leave-one-document-out over all 48 corpus documents, the worst fold gives
    0.7738, and deleting the 20 largest documents gives 0.7667. 0.70 sits under
    both, so an ordinary corpus edit cannot turn this red, while a real
    degradation of the ranking does.
    """
    a, _, _, _ = _auc_for(scored_suite, "all")
    assert a is not None, "AUC undefined: one class is empty"
    assert a >= AUC_FLOOR_ALL, (
        f"Lexical AUC over all labels fell below the recorded floor.\n"
        f"  AUC = {a:.4f}, floor {AUC_FLOOR_ALL}, recorded {MEASURED['all'][1]:.4f}\n"
        f"{_cohort_report(scored_suite, 'all')}"
    )


def test_lexical_auc_floor_human_baseline(scored_suite):
    """FLOOR, human-authored cohort only. Recorded 1.0000 over 10 cases.

    Asserted SEPARATELY from the full suite on purpose. 61 of the 76 labels are
    machine-generated and unreviewed; only these 15 carry human authority. If a
    future human review corrects generated labels, the full-suite AUC will move
    and this cohort will not, which is the signal worth having - a single blended
    number would hide it.

    Floor 0.85. With 3 BLOCK x 7 ALLOW = 21 pairs the AUC quantum is 1/21 =
    0.0476, so this floor is really "at most 3 of 21 pairs may invert". The
    measured 1.0000 rests on a +0.0034 margin (#4 at 0.5542 over #15 at 0.5508),
    so pinning at 1.0000 would go red on routine corpus edits; the worst
    single-document fold already inverts one pair.
    """
    a, g, pos, neg = _auc_for(scored_suite, "human")
    assert a is not None, (
        "AUC undefined for the human baseline cohort - one class is empty. With "
        "3 expected-BLOCK and 7 expected-ALLOW cases recorded, this means the "
        "cohort was not loaded correctly."
    )
    assert len(pos) >= 2 and len(neg) >= 2, (
        f"human cohort too small to mean anything: {len(pos)} BLOCK, {len(neg)} ALLOW"
    )
    assert a >= AUC_FLOOR_HUMAN, (
        f"Lexical AUC over the HUMAN-AUTHORED baseline fell below the recorded "
        f"floor. These are the only labels with human authority, so this is a "
        f"stronger signal than the full-suite figure.\n"
        f"  AUC = {a:.4f}, floor {AUC_FLOOR_HUMAN}, recorded "
        f"{MEASURED['human'][1]:.4f}\n"
        f"  that is {round((1.0 - a) * len(pos) * len(neg))} of "
        f"{len(pos) * len(neg)} BLOCK/ALLOW pairs ranked the wrong way\n"
        f"{_cohort_report(scored_suite, 'human')}"
    )


def test_generated_and_human_cohorts_are_reported_separately(scored_suite):
    """The generated cohort measured on its own, so label weakness stays visible.

    Not a tighter constraint than the two floors above - it is the third of the
    three readings scripts/calibration/report_metrics.py prints, kept here so
    that human review of the generated labels shows up as a visible change in
    THIS number rather than as a quiet shift in the blended one. Where the human
    and generated cohorts disagree, that disagreement is a finding about the
    labels, not noise to average away.
    """
    a_gen, _, pos_gen, neg_gen = _auc_for(scored_suite, "generated")
    a_hum, _, _, _ = _auc_for(scored_suite, "human")

    assert len(pos_gen) + len(neg_gen) == MEASURED["generated"][0], (
        f"generated cohort has {len(pos_gen) + len(neg_gen)} lexically-scored "
        f"cases, recorded {MEASURED['generated'][0]}"
    )
    assert a_gen is not None and a_hum is not None
    assert a_gen > DIRECTION_FLOOR, (
        f"Lexical AUC over the machine-generated labels is no better than "
        f"chance.\n  AUC = {a_gen:.4f}, required > {DIRECTION_FLOOR}\n"
        f"{_cohort_report(scored_suite, 'generated')}"
    )
    # The two cohorts must not silently diverge. A wide split means one of the
    # label sets is describing something different from the other, which is a
    # finding to investigate before either floor is trusted.
    assert abs(a_gen - a_hum) <= 0.35, (
        f"The human-authored and machine-generated cohorts disagree sharply "
        f"about how well the score ranks: human AUC {a_hum:.4f} vs generated "
        f"AUC {a_gen:.4f}. 61 of 76 labels are machine-generated and unreviewed, "
        f"so a split this wide means the floors above may be measuring the "
        f"labels rather than the scorer. Investigate before adjusting either.\n"
        f"{_cohort_report(scored_suite, 'human')}\n"
        f"{_cohort_report(scored_suite, 'generated')}"
    )


# =============================================================================
# 3. No unrecoverable BLOCK misses beyond the known set
# =============================================================================

def test_no_new_block_labelled_case_skips_the_llm(scored_suite):
    """THE ASSERTION THAT MATTERS MOST HERE.

    A BLOCK-labelled prompt that takes a needs_llm=False path is unrecoverable:
    the pre-classifier has decided, no reviewer sees the prompt, and nothing
    downstream re-examines it. Task 8.2 measured that set as exactly 6 of the 39
    BLOCK-labelled cases and this pins it, so any config or code change that adds
    a seventh fails here and names it.

    This is checked against the live pre_classify(), so it responds to all of the
    inputs that can move it: a threshold in config.py, the tiering in
    pre_classifier.py, the corpus, the stoplist, Presidio's entity coverage, and
    the saturation constant. Raising HYBRID_PUBLIC_THRESHOLD back to 0.30, for
    instance, re-enables semantic_confirmed_public and immediately adds #75 and
    #76 - both proposals to hand data to an outsider, both scoring low only
    because they use almost no corpus vocabulary. That is exactly the failure
    this test is here to make loud.

    Set equality is deliberate, in both directions. A case LEAVING the set is
    good news, but it still has to be recorded here on purpose rather than
    absorbed silently, or the pin stops describing anything.
    """
    actual = block_cases_skipping_llm(scored_suite)
    by_id = {r["id"]: r for r in scored_suite}

    new_misses = {k: v for k, v in actual.items() if k not in KNOWN_BLOCK_LABELLED_LLM_SKIPS}
    recovered = {k: v for k, v in KNOWN_BLOCK_LABELLED_LLM_SKIPS.items() if k not in actual}
    moved = {
        k: (KNOWN_BLOCK_LABELLED_LLM_SKIPS[k], v)
        for k, v in actual.items()
        if k in KNOWN_BLOCK_LABELLED_LLM_SKIPS and KNOWN_BLOCK_LABELLED_LLM_SKIPS[k] != v
    }

    if new_misses or recovered or moved:
        lines = [
            "The set of BLOCK-labelled cases that never reach the LLM has changed.",
            f"  pinned : {KNOWN_BLOCK_LABELLED_LLM_SKIPS}",
            f"  actual : {actual}",
            f"  live config: TFIDF_PUBLIC={config.TFIDF_PUBLIC_THRESHOLD} "
            f"TFIDF_ENTERPRISE={config.TFIDF_ENTERPRISE_THRESHOLD} "
            f"K={config.LEXICAL_SATURATION_K} "
            f"HYBRID_PUBLIC={config.HYBRID_PUBLIC_THRESHOLD} "
            f"HYBRID_ENTERPRISE={config.HYBRID_ENTERPRISE_THRESHOLD}",
        ]
        if new_misses:
            lines.append(
                "\n  *** REGRESSION: these BLOCK-labelled prompts became "
                "unrecoverable - no reviewer will ever see them ***"
            )
            for case_id, path in sorted(new_misses.items(), key=lambda kv: by_id[kv[0]]["num"]):
                r = by_id[case_id]
                lines += [
                    f"    {case_id} via {path}   lex={r['lex']:.4f} "
                    f"verdict={r['verdict']} hybrid={r['hybrid']} "
                    f"entities={r['entities']}",
                    f"        matched_terms={r['matched'][:10]}",
                    f"        {r['text'][:150]}",
                ]
        if moved:
            lines.append("\n  path changed for an already-known skip:")
            for case_id, (was, now) in sorted(moved.items()):
                lines.append(f"    {case_id}: {was} -> {now}")
        if recovered:
            lines.append(
                "\n  improvement: these now reach the LLM. Remove them from "
                "KNOWN_BLOCK_LABELLED_LLM_SKIPS deliberately, so the pin keeps "
                "describing reality:"
            )
            for case_id, path in sorted(recovered.items()):
                lines.append(f"    {case_id} (was {path}, now {by_id[case_id]['path']})")
        pytest.fail("\n".join(lines))


def test_secrets_skips_are_backed_by_a_presidio_detection(scored_suite):
    """The 5 by-design skips must be by design, not by coincidence.

    hard_block is the one no-LLM path where blocking a BLOCK-labelled prompt
    without review is correct, and the justification is specific: Presidio found
    a credential, so the detection itself is the evidence. That justification
    stops holding the moment a case takes hard_block without such a detection, so
    it is checked rather than assumed - otherwise "by design" becomes a label
    that quietly excuses whatever ends up on that path.
    """
    for r in scored_suite:
        if r["path"] == "hard_block":
            detected = set(r["entities"]) & SECRET_ENTITY_TYPES
            assert detected, (
                f"{r['id']} took hard_block with no credential entity detected "
                f"(entities={r['entities']}). hard_block skips the LLM on the "
                f"strength of Presidio's detection; without one there is no "
                f"evidence behind the block."
            )

    for case_id, path in KNOWN_BLOCK_LABELLED_LLM_SKIPS.items():
        if path in BY_DESIGN_NO_LLM_PATHS:
            r = next(x for x in scored_suite if x["id"] == case_id)
            assert r["path"] == path, f"{case_id} expected {path}, took {r['path']}"


def test_every_no_llm_path_is_accounted_for(scored_suite):
    """No decision path may skip the LLM without this file knowing about it.

    NO_LLM_PATHS in suite_metrics is what makes the pinned set above meaningful:
    a path missing from that set would let a BLOCK-labelled case skip the LLM
    while `block_cases_skipping_llm` reported nothing. So every path this run
    actually took with needs_llm=False must be a member.
    """
    unaccounted = sorted({
        r["path"] for r in scored_suite if r["needs_llm"] is False and r["path"] not in NO_LLM_PATHS
    })
    assert not unaccounted, (
        f"decision path(s) {unaccounted} returned needs_llm=False but are not "
        f"listed in suite_metrics.NO_LLM_PATHS. Until they are, a BLOCK-labelled "
        f"case taking one of them would skip the LLM without "
        f"test_no_new_block_labelled_case_skips_the_llm noticing. Add them there, "
        f"and re-measure KNOWN_BLOCK_LABELLED_LLM_SKIPS."
    )

    # And the converse: a path listed as skipping must never claim needs_llm=True,
    # or the pinned set would over-report and desensitise the assertion.
    contradictory = sorted({
        r["path"] for r in scored_suite if r["needs_llm"] is True and r["path"] in NO_LLM_PATHS
    })
    assert not contradictory, (
        f"decision path(s) {contradictory} returned needs_llm=True but are listed "
        f"in suite_metrics.NO_LLM_PATHS"
    )


# =============================================================================
# MUTATION CHECK (tasks 2.2 and 3.3 set this standard)
# =============================================================================
# A regression harness nobody has watched fail is a guess. This one was verified
# on 2026-08-01 against the actual pre-fix code, by reintroducing the original
# defect IN MEMORY - patching lexical_engine.STOPWORDS and LexicalEngine.score,
# reindexing, and substituting the result into pre_classifier so ROUTING was
# mutated too. No source file was modified.
#
# Baseline, for comparison:  all 0.8021   human 1.0000   generated 0.8097
#                            6 BLOCK-labelled cases skip the LLM
#
#   MUTANT A - the density normalization from Finding 2 restored,
#              normalized = raw_score / sum(tf * max_idf for tf in prompt_tf),
#              stoplist left in place:
#                all 0.4205 (gap -0.8209)   human 0.3810   generated 0.4398
#                BLOCK-labelled LLM skips 6 -> 8, newly unrecoverable: #27, #37
#              RED (5): points_the_right_way, auc_floor_all_labels,
#                       auc_floor_human_baseline, cohorts_reported_separately,
#                       no_new_block_labelled_case_skips_the_llm
#              Note the direction test fails here on the ALL cohort too, at
#              0.4205 - below 0.5, i.e. the score is inverted, which is the
#              defect class this file exists for.
#
#   MUTANT B - stoplist emptied (task 1.2 reverted), current normalization kept:
#                all 0.6145 (gap -0.7187)   human 0.8571   generated 0.6527
#                BLOCK-labelled LLM skips unchanged at 6
#              RED (2): auc_floor_all_labels (0.6145 < 0.70),
#                       auc_floor_human_baseline (0.8571 < 0.90, i.e. 3 of the
#                       21 human pairs inverted)
#              Not inverted, so the direction floor correctly holds: this half of
#              the task-1 fix degrades the ranking without reversing it, which
#              matches Finding 4's measurement that stopwords are not the half
#              that carries the correlation.
#
#   MUTANT A+B - both, i.e. the exact pre-task-1 scorer:
#                all 0.3156 (gap -0.9284)   human 0.1905   generated 0.3398
#                BLOCK-labelled LLM skips 6 -> 10, newly unrecoverable:
#                #27, #35, #37, #38
#              RED (5): the same five as mutant A, by much larger margins.
#              Human-baseline 0.1905 against Finding 1's reported 0.238; the two
#              differ because Finding 1 was measured on the original 15-case
#              suite before task 8.1 grew it, and 0.238 was the figure over its
#              10 non-secret cases. Same magnitude, same direction: strongly
#              inverted.
#
# Then restored and re-run: 10 passed, 0 failed, and the module globals were
# checked to be the original objects again.
#
# What the mutants also show is which assertions are load-bearing. The two
# preconditions tests and the two path-bookkeeping tests stay green under every
# mutant, because they check that the measurement is valid, not that it is good.
# That is their job; they are what stops the other five from passing vacuously.

# =============================================================================
# WHAT THIS FILE DOES NOT COVER
# =============================================================================
# - The hybrid and semantic scores have no floor here. Measured over the 38
#   tier-2 cases their AUC is 0.4872 and 0.3782 - at or below chance - so there
#   is nothing to defend yet. That is recorded in config.py and is why task 8.2
#   disabled the only tier-2 branch that skipped the LLM. A floor here would
#   assert a correlation the data does not show.
# - Final verdicts (SAFE / SANITIZE / BLOCK) are not asserted, because for the 68
#   cases that reach the LLM the verdict is the LLM's, and pinning it would mean
#   spending live model calls on every test run. Routing is the deterministic
#   part, and routing is what this file pins.
# - #68 is a coverage limit no threshold can close. It is pinned as a known miss
#   rather than left as a silent one; closing it needs an intent rule or the LLM,
#   not calibration.
