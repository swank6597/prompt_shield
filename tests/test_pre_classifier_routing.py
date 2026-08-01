# Feature: lexical-semantic-upgrade, Property 6: Pre-Classifier Priority Routing
# **Validates: Requirements 5.1, 5.2, 5.3, 5.5**
# **Validates: specs/lexical-semantic-fix/plan.md Task 2.1 (supersedes Requirement 5.4)**
# **Validates: specs/lexical-semantic-fix/plan.md Task 3.3 (supersedes Requirement 6.3)**
#
# Property 6: For any combination of (secrets, PII, lexical_verdict), the
# Pre-Classifier SHALL route according to strict priority order:
#   1. Secrets detected -> hard_block (always, regardless of other signals)
#   2. PII + PUBLIC verdict -> pii_only
#   3. PUBLIC verdict, no PII -> general_knowledge
#   4. ENTERPRISE_LIKELY verdict -> enterprise_lexical_needs_review (LLM called)
#   5. AMBIGUOUS verdict -> semantic engine invoked (needs_llm depends on hybrid)
#
# Property 6f (added by specs/lexical-semantic-fix Task 2.2, tightened by Task
# 3.3) states the safety invariant underneath items 1-5, in terms of evidence
# rather than path names: a decision taken on a RETRIEVAL SCORE may never skip
# the LLM while handing the policy engine an ECI that trips its architecture
# BLOCK rule. 6a-6e pin WHICH path is taken; 6f pins what a path is ALLOWED to
# conclude. Only 6f fails when a new fast path is added that self-asserts a
# verdict from a score, which is the defect class Tasks 2.1 and 3.3 removed.
#
# ── Traceability note on item 4 ───────────────────────────────────────────────
# Requirement 5.4 of specs/lexical-semantic-upgrade/requirements.md reads:
#
#   "WHEN the Lexical_Engine returns an ENTERPRISE_LIKELY verdict, THE
#    Pre_Classifier SHALL skip the LLM and return the enterprise_detected
#    decision path"
#
# That requirement is superseded and is NOT what this file asserts any more.
# specs/lexical-semantic-fix (Finding 1, Task 2.1) removed that fast path: a
# TF-IDF score measures vocabulary overlap with the knowledge corpus, which is
# a retrieval signal, not a disclosure judgement. The corpus documents OAuth
# 2.0 and GDPR, so generic public questions about them score highly too - case
# #9 ("in general terms, how does an OAuth 2.0 client_credentials grant work")
# scored 0.7200 and was deterministically BLOCKed with no LLM review. Skipping
# the LLM there let the pre-classifier assert containsInternalArchitecture at
# confidence 0.9, above rules.json's 0.7 block threshold, on evidence it does
# not have.
#
# Requirement 5.4 has deliberately been left unedited in the older spec (it is
# the historical record of what was built); the remediation plan is the current
# authority for this behavior. The conflict is real and intentional, not an
# oversight - see the report for Task 2.2.
#
# ── Traceability note on item 5 ───────────────────────────────────────────────
# The same supersession now applies one tier down. specs/lexical-semantic-
# upgrade/design.md (Property 8, Requirement 6.3) reads:
#
#   "If hybrid_score >= enterprise_threshold (default 0.55), the routing
#    decision SHALL be semantic_confirmed_enterprise with needs_llm=False"
#
# specs/lexical-semantic-fix Task 3.3 replaced that with
# enterprise_hybrid_needs_review and needs_llm=True. The reason is the same one
# as for 5.4, and the evidence is the case the old behavior blocked the first
# time it was ever able to run: suite case #10 ("what are NovaBank's three
# enterprise data classification levels...", expected ALLOW / WARN) scored
# lex=0.3781 AMBIGUOUS, sem=0.8890, hybrid=0.6846 and was deterministically
# BLOCKed at riskScore=54 with no review. It clears the threshold by +0.1346, so
# it is not reachable by retuning - and retuning to dodge one labelled case
# would be fitting to a single datapoint. HYBRID_* calibration belongs to Task
# 8.2 with a larger labelled set.
#
# 6.3 is likewise left unedited in the older spec as the historical record.

import os
import sys

_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "backend"))
_AI_DIR = os.path.join(_BACKEND_DIR, "ai")
_POLICY_DIR = os.path.join(_BACKEND_DIR, "policy")
for _d in (_BACKEND_DIR, _AI_DIR, _POLICY_DIR):
    if _d not in sys.path:
        sys.path.insert(0, _d)

from dataclasses import dataclass, field
from unittest.mock import patch, MagicMock

from hypothesis import given, settings, assume
from hypothesis import strategies as st

import config  # noqa: E402
from policy_engine import decide as decide_policy  # noqa: E402


# ---------------------------------------------------------------------------
# Dataclass mirroring LexicalResult for mocking
# ---------------------------------------------------------------------------

@dataclass
class MockLexicalResult:
    """Mock LexicalResult for controlled routing tests."""
    tfidf_score: float = 0.0
    verdict: str = "PUBLIC"
    top_docs: list = field(default_factory=list)
    matched_terms: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Constants matching pre_classifier.py
# ---------------------------------------------------------------------------

SECRET_ENTITY_TYPES = {
    "GITHUB_TOKEN", "OPENAI_API_KEY", "AWS_ACCESS_KEY",
    "AWS_SECRET_KEY", "PRIVATE_KEY", "JWT_TOKEN",
}

PII_ENTITY_TYPES = {
    "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "AADHAAR_NUMBER",
    "PASSPORT_NUMBER", "DRIVING_LICENSE", "PAN_NUMBER",
}

VALID_VERDICTS = ["PUBLIC", "ENTERPRISE_LIKELY", "AMBIGUOUS"]

# ── Classification of the no-LLM decision paths, for Property 6f ─────────────
#
# Paths where needs_llm=False rests on HARD EVIDENCE rather than on a score:
#   hard_block - Presidio actually matched a credential pattern. The entity
#                itself is the evidence; an LLM opinion cannot unmatch it.
#   trivial    - the prompt is trivially short with zero entities, so there is
#                nothing for the LLM to classify.
_HARD_EVIDENCE_PATHS = {"hard_block", "trivial"}

# ── The tier-2 carve-out is GONE (specs/lexical-semantic-fix Task 3.3) ───────
#
# Task 2.2 excluded the tier-2 paths from 6f via a _TIER2_PATHS constant, on the
# grounds that they require the lexical and semantic scores to agree and so are
# not a "lexical-only" signal. That exemption was explicitly recorded as not a
# full exoneration: semantic_confirmed_enterprise still self-asserted
# containsInternalArchitecture at confidence=0.9 from a score, and the path was
# only harmless because the semantic dependencies were not installed.
#
# Installing them (Task 3.1) made it fire, and it hard-BLOCKed suite case #10
# (expected ALLOW / WARN) at hybrid=0.6846 with no review. Task 3.3 routes that
# case to the LLM as enterprise_hybrid_needs_review, which removes the reason
# for the carve-out: the one tier-2 path that still skips the LLM,
# semantic_confirmed_public, asserts a SAFE ECI and therefore cannot trip the
# architecture BLOCK rule by construction.
#
# So 6f now covers EVERY no-LLM path except the two backed by hard evidence.
# That is the point of dropping the exemption rather than just re-labelling it:
# "two retrieval signals agreed" was never a different KIND of evidence from
# "one retrieval signal fired", only more of the same, and an exemption phrased
# by tier would have let the next hybrid fast path repeat the defect.

# ECI flags that rules.json's block_internal_architecture_or_code fires on.
# Asserted independently of the rule's confidence threshold so that retuning
# eci_min_confidence cannot silently disarm Property 6f.
_BLOCK_TRIPPING_ECI_FLAGS = ("containsInternalArchitecture", "containsSourceCode")

_ECI_BLOCK_RULE_ID = "block_internal_architecture_or_code"


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Strategy: generate a non-empty set of secret entity types
secret_entities_st = st.lists(
    st.sampled_from(sorted(SECRET_ENTITY_TYPES)),
    min_size=1,
    max_size=len(SECRET_ENTITY_TYPES),
    unique=True,
).map(set)

# Strategy: generate a non-empty set of PII entity types (non-secret)
pii_entities_st = st.lists(
    st.sampled_from(sorted(PII_ENTITY_TYPES)),
    min_size=1,
    max_size=len(PII_ENTITY_TYPES),
    unique=True,
).map(set)

# Strategy: generate a lexical verdict
verdict_st = st.sampled_from(VALID_VERDICTS)

# Strategy: generate a TF-IDF score in [0.0, 1.0]
tfidf_score_st = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)

# Strategy: generate a prompt string
prompt_st = st.text(min_size=1, max_size=100)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_presidio_result(entity_types: set) -> dict:
    """Build a mock presidio_result dict from a set of entity types."""
    entities = [{"entity_type": et, "start": 0, "end": 5, "score": 0.99} for et in entity_types]
    return {
        "entityCount": len(entities),
        "maskedText": "test masked text",
        "entities": entities,
    }


def _make_mock_lexical_engine(verdict: str, tfidf_score: float):
    """Create a mock lexical engine that returns a controlled LexicalResult."""
    mock_engine = MagicMock()
    mock_engine.score.return_value = MockLexicalResult(
        tfidf_score=tfidf_score,
        verdict=verdict,
        top_docs=[{"filename": "test.md", "score": tfidf_score}],
        matched_terms=["test_term"],
    )
    return mock_engine


def _make_mock_semantic_engine(semantic_score: float = 0.5):
    """Create a mock semantic engine that returns a controlled SemanticResult."""
    mock_engine = MagicMock()
    mock_result = MagicMock()
    mock_result.semantic_score = semantic_score
    mock_result.top_chunks = [{"text": "chunk", "score": semantic_score}]
    mock_result.source_docs = ["test.md"]
    mock_engine.search.return_value = mock_result
    mock_engine.available = True
    return mock_engine


def _call_pre_classify(prompt, presidio_result, verdict, tfidf_score,
                       semantic_available=True, semantic_score=0.5):
    """
    Call pre_classify with mocked module-level globals.

    Patches the pre_classifier module's globals to control routing.
    Also patches is_trivial_prompt to always return False so the trivial
    path does not interfere with testing the lexical/semantic routing.
    """
    import ai.pre_classifier as pre_classifier_module

    mock_lexical = _make_mock_lexical_engine(verdict, tfidf_score)
    mock_semantic = _make_mock_semantic_engine(semantic_score)

    with patch.object(pre_classifier_module, '_lexical_available', True), \
         patch.object(pre_classifier_module, '_lexical_engine_instance', mock_lexical), \
         patch.object(pre_classifier_module, '_semantic_available', semantic_available), \
         patch.object(pre_classifier_module, '_semantic_engine_instance', mock_semantic), \
         patch.object(config, 'USE_LEGACY_SEARCH', False), \
         patch("ai.pre_classifier.is_trivial_prompt", return_value=False):
        result = pre_classifier_module.pre_classify(prompt, "masked text", presidio_result)

    return result


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------

@given(
    secrets=secret_entities_st,
    extra_pii=st.one_of(st.just(set()), pii_entities_st),
    verdict=verdict_st,
    tfidf_score=tfidf_score_st,
    prompt=prompt_st,
)
@settings(max_examples=200, deadline=None)
def test_secrets_always_produce_hard_block(secrets, extra_pii, verdict, tfidf_score, prompt):
    """
    Property 6a: Secrets always produce hard_block regardless of other signals.

    When Presidio detects any secret entity types, the pre-classifier SHALL
    always return decision_path='hard_block' with needs_llm=False, regardless
    of the lexical verdict, PII presence, or tfidf_score.
    """
    # Combine secrets with optional PII — secrets should STILL win
    all_entities = secrets | extra_pii
    presidio_result = _build_presidio_result(all_entities)

    result = _call_pre_classify(prompt, presidio_result, verdict, tfidf_score)

    assert result["decision_path"] == "hard_block", (
        f"Expected hard_block when secrets={secrets}, "
        f"but got decision_path={result['decision_path']!r}"
    )
    assert result["needs_llm"] is False, (
        f"Expected needs_llm=False for hard_block, got {result['needs_llm']}"
    )


@given(
    pii=pii_entities_st,
    tfidf_score=tfidf_score_st,
    prompt=prompt_st,
)
@settings(max_examples=200, deadline=None)
def test_pii_with_public_verdict_produces_pii_only(pii, tfidf_score, prompt):
    """
    Property 6b: PII + PUBLIC verdict -> pii_only.

    When Presidio detects PII (non-secret) entities and the lexical engine
    returns a PUBLIC verdict, the pre-classifier SHALL return
    decision_path='pii_only' with needs_llm=False.
    """
    presidio_result = _build_presidio_result(pii)

    result = _call_pre_classify(prompt, presidio_result, "PUBLIC", tfidf_score)

    assert result["decision_path"] == "pii_only", (
        f"Expected pii_only when PII={pii} and verdict=PUBLIC, "
        f"but got decision_path={result['decision_path']!r}"
    )
    assert result["needs_llm"] is False, (
        f"Expected needs_llm=False for pii_only, got {result['needs_llm']}"
    )


@given(
    tfidf_score=tfidf_score_st,
    prompt=prompt_st,
)
@settings(max_examples=200, deadline=None)
def test_public_no_pii_produces_general_knowledge(tfidf_score, prompt):
    """
    Property 6c: PUBLIC verdict + no PII -> general_knowledge.

    When no entities are detected and the lexical engine returns a PUBLIC
    verdict, the pre-classifier SHALL return decision_path='general_knowledge'
    with needs_llm=False.
    """
    presidio_result = _build_presidio_result(set())

    result = _call_pre_classify(prompt, presidio_result, "PUBLIC", tfidf_score)

    assert result["decision_path"] == "general_knowledge", (
        f"Expected general_knowledge when no PII and verdict=PUBLIC, "
        f"but got decision_path={result['decision_path']!r}"
    )
    assert result["needs_llm"] is False, (
        f"Expected needs_llm=False for general_knowledge, got {result['needs_llm']}"
    )


@given(
    entities=st.one_of(st.just(set()), pii_entities_st),
    tfidf_score=tfidf_score_st,
    prompt=prompt_st,
)
@settings(max_examples=200, deadline=None)
def test_enterprise_likely_routes_to_llm_review(entities, tfidf_score, prompt):
    """
    Property 6d: ENTERPRISE_LIKELY verdict -> enterprise_lexical_needs_review.

    When the lexical engine returns an ENTERPRISE_LIKELY verdict, the
    pre-classifier SHALL return decision_path='enterprise_lexical_needs_review'
    with needs_llm=True and pre_eci=None, regardless of PII presence.

    Renamed from test_enterprise_likely_produces_enterprise_detected. The old
    name described the behavior removed by specs/lexical-semantic-fix Task 2.1
    and had become a misnomer.
    """
    presidio_result = _build_presidio_result(entities)

    result = _call_pre_classify(prompt, presidio_result, "ENTERPRISE_LIKELY", tfidf_score)

    # WHY this changed from 'enterprise_detected':
    # A TF-IDF score is a retrieval signal - it says the prompt shares
    # vocabulary with the knowledge corpus. It is not a disclosure judgement.
    # The corpus documents OAuth 2.0 and GDPR, so generic questions about those
    # topics score just as highly as genuinely internal ones (measured: the
    # public "how does an OAuth 2.0 client_credentials grant work" outscored
    # every expected-BLOCK case in the suite). Crossing the threshold therefore
    # earns a prompt an LLM review; it must not decide the outcome of that
    # review.
    assert result["decision_path"] == "enterprise_lexical_needs_review", (
        f"Expected enterprise_lexical_needs_review when verdict=ENTERPRISE_LIKELY, "
        f"but got decision_path={result['decision_path']!r}"
    )

    # WHY needs_llm flipped False -> True:
    # This is the whole point of the fix. Skipping the LLM here made the
    # lexical score the sole and final arbiter, with no second opinion in the
    # pipeline capable of overriding it.
    assert result["needs_llm"] is True, (
        f"Expected needs_llm=True for enterprise_lexical_needs_review, "
        f"got {result['needs_llm']}"
    )

    # WHY pre_eci must be None:
    # The removed branch returned a synthetic ECI from _build_enterprise_eci()
    # with containsInternalArchitecture=True at confidence=0.9. rules.json's
    # block_internal_architecture_or_code fires on that flag at
    # eci_min_confidence=0.7, so one threshold crossing became a deterministic
    # BLOCK. Asserting pre_eci is None pins the contract that the
    # pre-classifier hands the LLM an open question rather than a verdict it
    # has no evidence for - and it fails if the synthetic ECI comes back even
    # under a different decision_path label.
    assert result["pre_eci"] is None, (
        f"Expected pre_eci=None when routing to the LLM; the pre-classifier "
        f"must not pre-judge the outcome. Got {result['pre_eci']!r}"
    )

    # The score itself is still carried forward: it is legitimate evidence for
    # the LLM and for the audit trail, just not a verdict on its own.
    assert result["lexical_result"] is not None, (
        "Expected lexical_result to be preserved for LLM context and audit"
    )
    assert result["lexical_result"]["verdict"] == "ENTERPRISE_LIKELY"


@given(
    entities=st.one_of(st.just(set()), pii_entities_st),
    tfidf_score=tfidf_score_st,
    prompt=prompt_st,
)
@settings(max_examples=200, deadline=None)
def test_ambiguous_invokes_semantic_engine(entities, tfidf_score, prompt):
    """
    Property 6e: AMBIGUOUS verdict -> semantic engine invoked.

    When the lexical engine returns an AMBIGUOUS verdict, the pre-classifier
    SHALL invoke the semantic engine. The result will be one of:
    semantic_confirmed_public, enterprise_hybrid_needs_review, or
    true_ambiguity depending on the hybrid score.
    """
    presidio_result = _build_presidio_result(entities)

    result = _call_pre_classify(
        prompt, presidio_result, "AMBIGUOUS", tfidf_score,
        semantic_available=True, semantic_score=0.5,
    )

    # When AMBIGUOUS, the decision should be one of the tier-2 paths.
    #
    # 'semantic_confirmed_enterprise' was replaced by
    # 'enterprise_hybrid_needs_review' in specs/lexical-semantic-fix Task 3.3:
    # the old path skipped the LLM and asserted a verdict from the hybrid
    # score, which is the same category error Task 2.1 removed from the
    # lexical tier. It is not accepted here as an alternative spelling,
    # because a revert would then pass this property silently - Property 6f
    # is what fails on the ECI, and this set is what fails on the label.
    valid_ambiguous_paths = {
        "semantic_confirmed_public",
        "enterprise_hybrid_needs_review",
        "true_ambiguity",
    }
    assert result["decision_path"] in valid_ambiguous_paths, (
        f"Expected one of {valid_ambiguous_paths} when verdict=AMBIGUOUS, "
        f"but got decision_path={result['decision_path']!r}"
    )
    # Hybrid score should be populated
    assert result["hybrid_score"] is not None, (
        f"Expected hybrid_score to be populated for AMBIGUOUS path, got None"
    )
    # Semantic result should be populated
    assert result["semantic_result"] is not None, (
        f"Expected semantic_result to be populated for AMBIGUOUS path, got None"
    )


@given(
    secrets=st.one_of(st.just(set()), secret_entities_st),
    pii=st.one_of(st.just(set()), pii_entities_st),
    verdict=verdict_st,
    tfidf_score=tfidf_score_st,
    semantic_available=st.booleans(),
    semantic_score=st.floats(min_value=0.0, max_value=1.0,
                             allow_nan=False, allow_infinity=False),
    prompt=prompt_st,
)
@settings(max_examples=300, deadline=None)
def test_retrieval_signal_never_produces_unreviewable_block(
    secrets, pii, verdict, tfidf_score, semantic_available, semantic_score, prompt
):
    """
    Property 6f: No retrieval signal may produce an unreviewable BLOCK.

    Over the full cross product of (secrets, PII, lexical verdict, TF-IDF
    score, semantic availability, semantic score): whenever the pre-classifier
    skips the LLM on the strength of a retrieval score - lexical, semantic, or
    the hybrid of the two - the pre_eci it supplies to the policy engine SHALL
    NOT trip rules.json's block_internal_architecture_or_code. needs_llm=False
    is only permitted to reach that BLOCK when it rests on hard evidence: a
    credential Presidio actually matched, or a trivially empty prompt.

    **Validates: specs/lexical-semantic-fix/plan.md Task 2.1**
    **Validates: specs/lexical-semantic-fix/plan.md Task 3.3**

    Renamed from test_lexical_only_signal_never_produces_unreviewable_block.
    Task 2.2 scoped this property to tier-1 and exempted the tier-2 paths,
    because at the time "the lexical and semantic scores had to agree first"
    read like a different class of evidence. Task 3.3 established it is not:
    embedding similarity is a retrieval signal exactly as TF-IDF is, and two
    retrieval signals agreeing makes the retrieval more confident, not the
    disclosure judgement more valid. MiniLM scored suite case #10 at 0.8890
    against data-classification.md precisely because the question genuinely IS
    about a documented topic - which says nothing about whether answering it
    discloses anything. With the exemption dropped, "lexical-only" in the old
    name was both inaccurate and narrower than what is now asserted.

    Why this is stated as an evidence invariant and not as a decision_path
    string comparison: 6a-6e assert that specific inputs map to specific path
    names, so any of them can be "fixed" by editing the expected string, and
    none of them would notice a NEW fast path that repeats the mistake. The
    defect in Finding 1 was not a wrong label - it was a claim
    (containsInternalArchitecture at confidence 0.9) made on the basis of
    vocabulary overlap with the corpus, then acted on with no review. It then
    recurred verbatim on the hybrid path the moment that path became
    reachable, which is the argument for phrasing 6f by evidence: the same
    assertion catches both without being rewritten.

    Deliberately NOT asserted: that the final policy decision is never BLOCK.
    On the pii_only path, enough genuine Presidio entities push
    compute_risk_score() past block_critical_aggregate_risk's threshold of 80.
    That BLOCK is driven by detected entities - hard evidence - not by a
    retrieval score, so it is outside this property. Narrowing the assertion to
    the ECI-driven rule keeps the property about the signal under test.
    """
    entity_types = secrets | pii
    presidio_result = _build_presidio_result(entity_types)

    result = _call_pre_classify(
        prompt, presidio_result, verdict, tfidf_score,
        semantic_available=semantic_available, semantic_score=semantic_score,
    )

    if result["needs_llm"]:
        # The LLM will supply the ECI, so the pre-classifier must not have
        # pre-filled one; otherwise a caller could use the pre-judgement and
        # the review would be decorative.
        assert result["pre_eci"] is None, (
            f"decision_path={result['decision_path']!r} routes to the LLM but "
            f"still pre-filled an ECI: {result['pre_eci']!r}"
        )
        return

    path = result["decision_path"]

    if path in _HARD_EVIDENCE_PATHS:
        # The carve-out only holds if the hard evidence is really there. Note
        # that 'trivial' is unreachable in this property: _call_pre_classify
        # patches is_trivial_prompt to return False, so hard_block is the only
        # legitimate hard-evidence path here.
        assert path == "hard_block" and secrets, (
            f"decision_path={path!r} skipped the LLM claiming hard evidence, "
            f"but the detected entities were {sorted(entity_types)} "
            f"(secrets={sorted(secrets)}). Only a genuinely detected credential "
            f"justifies this path."
        )
        return

    # ── Score-driven decision: the LLM was skipped on a retrieval signal ─────
    # Reached by every remaining no-LLM path, tier-1 and tier-2 alike. No
    # exemption list here on purpose: an exemption keyed on which tier raised
    # the flag is exactly what let the hybrid path keep asserting
    # containsInternalArchitecture=True at confidence 0.9 through Task 2.2.
    eci = result["pre_eci"]
    assert eci is not None, (
        f"decision_path={path!r} skipped the LLM but supplied no ECI, so the "
        f"policy engine has nothing to decide from"
    )

    for flag in _BLOCK_TRIPPING_ECI_FLAGS:
        assert eci.get(flag) is not True, (
            f"decision_path={path!r} skipped the LLM and asserted {flag}=True "
            f"from a retrieval signal (verdict={verdict}, tfidf={tfidf_score:.4f}, "
            f"semantic={semantic_score:.4f}, semantic_available={semantic_available}). "
            f"TF-IDF measures vocabulary overlap with the knowledge corpus and "
            f"embedding similarity measures resemblance to it; both are "
            f"retrieval signals, not evidence of disclosure - the corpus "
            f"documents OAuth 2.0, GDPR and its own data-classification policy, "
            f"so generic public questions score highly too. This claim must be "
            f"made by a reviewer, not by a threshold crossing."
        )

    detection = {
        "entityCount": presidio_result["entityCount"],
        "entityTypes": sorted(entity_types),
    }
    policy_result = decide_policy(detection, eci)

    assert _ECI_BLOCK_RULE_ID not in policy_result["matchedRules"], (
        f"decision_path={path!r} skipped the LLM and still tripped "
        f"{_ECI_BLOCK_RULE_ID} (decision={policy_result['decision']}, "
        f"matchedRules={policy_result['matchedRules']}). That is a BLOCK no "
        f"reviewer ever saw, produced by a retrieval threshold crossing "
        f"(verdict={verdict}, tfidf={tfidf_score:.4f}, "
        f"semantic={semantic_score:.4f})."
    )
