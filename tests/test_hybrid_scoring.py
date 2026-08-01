# Feature: lexical-semantic-upgrade, Property 7: Hybrid Score Formula Correctness
"""
Property 7: Hybrid Score Formula Correctness

For any pair of TF-IDF score and semantic similarity score (both in [0.0, 1.0]),
the hybrid score SHALL equal lexical_weight * tfidf_score + semantic_weight * semantic_score
where weights are the configured values (default 0.4 and 0.6 respectively).

Validates: Requirements 6.1
"""

import sys
import os
import math

# Add backend directory to path for imports
_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "backend"))
_AI_DIR = os.path.join(_BACKEND_DIR, "ai")
for _d in (_BACKEND_DIR, _AI_DIR):
    if _d not in sys.path:
        sys.path.insert(0, _d)

from hypothesis import given, settings, assume
from hypothesis.strategies import floats


# --- Pure implementation of the hybrid score formula (mirrors pre_classifier logic) ---

def compute_hybrid_score(
    tfidf_score: float,
    semantic_score: float,
    lexical_weight: float,
    semantic_weight: float,
) -> float:
    """
    Compute the hybrid score as a weighted combination of lexical and semantic scores.
    This mirrors the formula used in pre_classifier.py.
    """
    return lexical_weight * tfidf_score + semantic_weight * semantic_score


# --- Strategies ---

# Scores are floats in [0.0, 1.0], excluding NaN/Inf
score_strategy = floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)

# Weights are positive floats that sum to approximately 1.0
# We generate the lexical weight and derive the semantic weight
weight_strategy = floats(min_value=0.01, max_value=0.99, allow_nan=False, allow_infinity=False)


# --- Property Tests ---


@settings(max_examples=200, deadline=None)
@given(tfidf_score=score_strategy, semantic_score=score_strategy)
def test_hybrid_score_formula_with_default_weights(tfidf_score: float, semantic_score: float):
    """
    **Validates: Requirements 6.1**

    With default weights (0.4 lexical, 0.6 semantic), the hybrid score SHALL equal
    0.4 * tfidf_score + 0.6 * semantic_score.
    """
    import config

    lexical_weight = config.HYBRID_LEXICAL_WEIGHT  # default 0.4
    semantic_weight = config.HYBRID_SEMANTIC_WEIGHT  # default 0.6

    hybrid = compute_hybrid_score(tfidf_score, semantic_score, lexical_weight, semantic_weight)
    expected = lexical_weight * tfidf_score + semantic_weight * semantic_score

    assert math.isclose(hybrid, expected, rel_tol=1e-9), (
        f"Hybrid score mismatch: got {hybrid}, expected {expected} "
        f"(tfidf={tfidf_score}, semantic={semantic_score}, "
        f"lex_w={lexical_weight}, sem_w={semantic_weight})"
    )


@settings(max_examples=200, deadline=None)
@given(
    tfidf_score=score_strategy,
    semantic_score=score_strategy,
    lexical_weight=weight_strategy,
)
def test_hybrid_score_formula_with_configurable_weights(
    tfidf_score: float, semantic_score: float, lexical_weight: float
):
    """
    **Validates: Requirements 6.1**

    For any pair of scores in [0.0, 1.0] and any valid weight pair that sums to 1.0,
    hybrid_score SHALL equal lexical_weight * tfidf_score + semantic_weight * semantic_score.
    """
    semantic_weight = 1.0 - lexical_weight

    hybrid = compute_hybrid_score(tfidf_score, semantic_score, lexical_weight, semantic_weight)
    expected = lexical_weight * tfidf_score + semantic_weight * semantic_score

    assert math.isclose(hybrid, expected, rel_tol=1e-9), (
        f"Hybrid score mismatch: got {hybrid}, expected {expected} "
        f"(tfidf={tfidf_score}, semantic={semantic_score}, "
        f"lex_w={lexical_weight}, sem_w={semantic_weight})"
    )


@settings(max_examples=200, deadline=None)
@given(tfidf_score=score_strategy, semantic_score=score_strategy)
def test_hybrid_score_bounded_zero_to_one(tfidf_score: float, semantic_score: float):
    """
    **Validates: Requirements 6.1**

    When weights sum to 1.0 and both input scores are in [0.0, 1.0],
    the hybrid score SHALL also be in [0.0, 1.0].
    """
    import config

    lexical_weight = config.HYBRID_LEXICAL_WEIGHT
    semantic_weight = config.HYBRID_SEMANTIC_WEIGHT

    hybrid = compute_hybrid_score(tfidf_score, semantic_score, lexical_weight, semantic_weight)

    assert 0.0 <= hybrid <= 1.0, (
        f"Hybrid score out of bounds: {hybrid} "
        f"(tfidf={tfidf_score}, semantic={semantic_score}, "
        f"lex_w={lexical_weight}, sem_w={semantic_weight})"
    )


@settings(max_examples=200, deadline=None)
@given(
    tfidf_score=score_strategy,
    semantic_score=score_strategy,
    lexical_weight=weight_strategy,
)
def test_hybrid_score_monotonicity(
    tfidf_score: float, semantic_score: float, lexical_weight: float
):
    """
    **Validates: Requirements 6.1**

    Increasing either input score (while holding the other constant)
    SHALL NOT decrease the hybrid score. The formula is monotonically non-decreasing
    in both inputs when weights are positive.
    """
    semantic_weight = 1.0 - lexical_weight

    hybrid_base = compute_hybrid_score(tfidf_score, semantic_score, lexical_weight, semantic_weight)

    # Increasing tfidf_score should not decrease hybrid
    higher_tfidf = min(tfidf_score + 0.1, 1.0)
    hybrid_higher_tfidf = compute_hybrid_score(higher_tfidf, semantic_score, lexical_weight, semantic_weight)
    assert hybrid_higher_tfidf >= hybrid_base - 1e-9, (
        f"Hybrid not monotonic in tfidf: base={hybrid_base}, higher={hybrid_higher_tfidf}"
    )

    # Increasing semantic_score should not decrease hybrid
    higher_semantic = min(semantic_score + 0.1, 1.0)
    hybrid_higher_semantic = compute_hybrid_score(tfidf_score, higher_semantic, lexical_weight, semantic_weight)
    assert hybrid_higher_semantic >= hybrid_base - 1e-9, (
        f"Hybrid not monotonic in semantic: base={hybrid_base}, higher={hybrid_higher_semantic}"
    )


# =============================================================================
# Feature: lexical-semantic-upgrade, Property 8: Hybrid Routing Threshold Consistency
# =============================================================================
"""
Property 8: Hybrid Routing Threshold Consistency

For any hybrid score in [0.0, 1.0] and any valid threshold pair where
public_threshold < enterprise_threshold, the routing decision SHALL be
exactly one of:
  - semantic_confirmed_public (needs_llm=False) when hybrid_score < public_threshold
  - enterprise_hybrid_needs_review (needs_llm=True) when hybrid_score >= enterprise_threshold
  - true_ambiguity (needs_llm=True) when public_threshold <= hybrid_score < enterprise_threshold

The three cases are mutually exclusive and exhaustive.

Validates: Requirements 6.2, 6.4
Validates: specs/lexical-semantic-fix/plan.md Task 3.3 (supersedes Requirement 6.3)

── Why the enterprise case changed ──────────────────────────────────────────
Requirement 6.3 specified semantic_confirmed_enterprise with needs_llm=False.
specs/lexical-semantic-fix Task 3.3 replaced it with
enterprise_hybrid_needs_review and needs_llm=True. Skipping the LLM there let
the pre-classifier hand the policy engine a synthetic ECI asserting
containsInternalArchitecture=True at confidence 0.9, which rules.json blocks on
at eci_min_confidence=0.7 - a deterministic BLOCK from a score, with no review.

The substantive reason: embedding similarity is a RETRIEVAL signal, exactly as
TF-IDF is (Task 2.1 removed the identical construct from the lexical tier). A
high cosine score means the prompt resembles a document in the corpus, i.e. it
is ABOUT a documented topic - which is not evidence that answering it discloses
anything. Two retrieval signals agreeing makes the retrieval more confident, not
the disclosure judgement more valid.

Measured, the first time this path was ever reachable (the semantic dependencies
were only installed in Task 3.1): suite case #10, "what are NovaBank's three
enterprise data classification levels", expected ALLOW / WARN, scored
lex=0.3781 AMBIGUOUS / sem=0.8890 / hybrid=0.6846 and was BLOCKed at
riskScore=54 with no LLM review. It clears the 0.55 threshold by +0.1346, so
this is not a calibration miss; HYBRID_* tuning belongs to Task 8.2.

Note that only the PUBLIC branch still skips the LLM. That asymmetry is
deliberate: asserting SAFE from a low score errs toward review-by-the-user
downstream, while asserting ENTERPRISE from a high score ends the pipeline in a
BLOCK nobody can appeal.
"""


# --- Pure implementation of routing decision (mirrors pre_classifier logic) ---

def route_by_hybrid_score(hybrid_score: float, public_threshold: float, enterprise_threshold: float):
    """
    Determine routing decision based on hybrid score and thresholds.
    Returns (decision_path, needs_llm).

    Mirrors the tier-2 branch of ai/pre_classifier.pre_classify(). The
    enterprise arm returns needs_llm=True since specs/lexical-semantic-fix
    Task 3.3 - see the module docstring above for why.
    """
    if hybrid_score < public_threshold:
        return "semantic_confirmed_public", False
    elif hybrid_score >= enterprise_threshold:
        return "enterprise_hybrid_needs_review", True
    else:
        return "true_ambiguity", True


# --- Strategies for Property 8 ---

# Hybrid scores in [0.0, 1.0]
hybrid_score_strategy = floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)

# Thresholds: public must be strictly less than enterprise, both in (0.0, 1.0)
threshold_strategy = floats(min_value=0.01, max_value=0.99, allow_nan=False, allow_infinity=False)


# --- Property 8 Tests ---


@settings(max_examples=200, deadline=None)
@given(hybrid_score=hybrid_score_strategy)
def test_hybrid_routing_with_default_thresholds(hybrid_score: float):
    """
    **Validates: Requirements 6.2, 6.4**
    **Validates: specs/lexical-semantic-fix/plan.md Task 3.3**

    With default thresholds (public=0.30, enterprise=0.55), the routing decision
    SHALL match the expected case based on threshold boundaries.

    This file tests the threshold ARITHMETIC against a pure mirror of the
    branch. The real pre_classify() is exercised on the same paths by
    tests/test_pre_classifier_routing.py Properties 6e and 6f - 6f is the one
    that fails if a path skips the LLM with a BLOCK-tripping ECI.
    """
    import config

    public_threshold = config.HYBRID_PUBLIC_THRESHOLD  # default 0.30
    enterprise_threshold = config.HYBRID_ENTERPRISE_THRESHOLD  # default 0.55

    decision_path, needs_llm = route_by_hybrid_score(hybrid_score, public_threshold, enterprise_threshold)

    if hybrid_score < public_threshold:
        assert decision_path == "semantic_confirmed_public", (
            f"Expected semantic_confirmed_public for score {hybrid_score} < {public_threshold}, "
            f"got {decision_path}"
        )
        assert needs_llm is False, (
            f"Expected needs_llm=False for semantic_confirmed_public, got {needs_llm}"
        )
    elif hybrid_score >= enterprise_threshold:
        # WHY this is enterprise_hybrid_needs_review with needs_llm=True and not
        # semantic_confirmed_enterprise with needs_llm=False (Requirement 6.3):
        # a high hybrid score is two retrieval signals agreeing that the prompt
        # resembles the corpus. That is a reason to review it, not a verdict on
        # whether it discloses anything. See the Property 8 docstring for the
        # measured case (#10, expected ALLOW / WARN, BLOCKed at hybrid=0.6846).
        assert decision_path == "enterprise_hybrid_needs_review", (
            f"Expected enterprise_hybrid_needs_review for score {hybrid_score} >= "
            f"{enterprise_threshold}, got {decision_path}"
        )
        assert needs_llm is True, (
            f"Expected needs_llm=True for enterprise_hybrid_needs_review, got {needs_llm}"
        )
    else:
        assert decision_path == "true_ambiguity", (
            f"Expected true_ambiguity for score {hybrid_score} in [{public_threshold}, {enterprise_threshold}), "
            f"got {decision_path}"
        )
        assert needs_llm is True, (
            f"Expected needs_llm=True for true_ambiguity, got {needs_llm}"
        )


@settings(max_examples=200, deadline=None)
@given(
    hybrid_score=hybrid_score_strategy,
    public_threshold=threshold_strategy,
    enterprise_threshold=threshold_strategy,
)
def test_hybrid_routing_with_configurable_thresholds(
    hybrid_score: float, public_threshold: float, enterprise_threshold: float
):
    """
    **Validates: Requirements 6.2, 6.4**
    **Validates: specs/lexical-semantic-fix/plan.md Task 3.3**

    For any valid threshold pair (public < enterprise) and any hybrid score in [0.0, 1.0],
    the routing decision SHALL match exactly one of the three cases.
    """
    # Ensure public_threshold < enterprise_threshold
    assume(public_threshold < enterprise_threshold)

    decision_path, needs_llm = route_by_hybrid_score(hybrid_score, public_threshold, enterprise_threshold)

    if hybrid_score < public_threshold:
        assert decision_path == "semantic_confirmed_public", (
            f"Expected semantic_confirmed_public for score {hybrid_score} < {public_threshold}, "
            f"got {decision_path}"
        )
        assert needs_llm is False, (
            f"Expected needs_llm=False for semantic_confirmed_public, got {needs_llm}"
        )
    elif hybrid_score >= enterprise_threshold:
        # Task 3.3: routes to review rather than self-asserting an enterprise
        # verdict, at every threshold pair - not just the configured default.
        # See the Property 8 docstring.
        assert decision_path == "enterprise_hybrid_needs_review", (
            f"Expected enterprise_hybrid_needs_review for score {hybrid_score} >= "
            f"{enterprise_threshold}, got {decision_path}"
        )
        assert needs_llm is True, (
            f"Expected needs_llm=True for enterprise_hybrid_needs_review, got {needs_llm}"
        )
    else:
        assert decision_path == "true_ambiguity", (
            f"Expected true_ambiguity for score {hybrid_score} in [{public_threshold}, {enterprise_threshold}), "
            f"got {decision_path}"
        )
        assert needs_llm is True, (
            f"Expected needs_llm=True for true_ambiguity, got {needs_llm}"
        )


@settings(max_examples=200, deadline=None)
@given(
    hybrid_score=hybrid_score_strategy,
    public_threshold=threshold_strategy,
    enterprise_threshold=threshold_strategy,
)
def test_hybrid_routing_mutually_exclusive_and_exhaustive(
    hybrid_score: float, public_threshold: float, enterprise_threshold: float
):
    """
    **Validates: Requirements 6.2, 6.4**
    **Validates: specs/lexical-semantic-fix/plan.md Task 3.3**

    For any hybrid score and valid threshold pair, exactly one of the three routing
    conditions is true: the cases are mutually exclusive and exhaustive.
    """
    assume(public_threshold < enterprise_threshold)

    # Count how many conditions match
    is_public = hybrid_score < public_threshold
    is_enterprise = hybrid_score >= enterprise_threshold
    is_ambiguous = (hybrid_score >= public_threshold) and (hybrid_score < enterprise_threshold)

    matching_count = sum([is_public, is_enterprise, is_ambiguous])

    assert matching_count == 1, (
        f"Expected exactly 1 matching condition, got {matching_count} "
        f"(public={is_public}, enterprise={is_enterprise}, ambiguous={is_ambiguous}) "
        f"for score={hybrid_score}, thresholds=({public_threshold}, {enterprise_threshold})"
    )

    # Also verify the routing function agrees with the condition
    decision_path, needs_llm = route_by_hybrid_score(hybrid_score, public_threshold, enterprise_threshold)

    if is_public:
        assert decision_path == "semantic_confirmed_public", (
            f"Routing mismatch: condition says public but got {decision_path}"
        )
    elif is_enterprise:
        # Renamed by Task 3.3: the enterprise arm requests a review instead of
        # asserting a verdict. Exclusivity/exhaustivity is unchanged.
        assert decision_path == "enterprise_hybrid_needs_review", (
            f"Routing mismatch: condition says enterprise but got {decision_path}"
        )
    else:
        assert decision_path == "true_ambiguity", (
            f"Routing mismatch: condition says ambiguous but got {decision_path}"
        )
