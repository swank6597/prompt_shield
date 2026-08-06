# Feature: lexical-semantic-upgrade, Task 9.3: Integration tests for end-to-end routing decisions
# **Validates: Requirements 8.1, 8.2, 8.3, 9.1, 9.2**
#
# Tests the full pipeline: Presidio -> Pre-Classifier -> (conditional LLM) -> Policy
# by mocking external services (Presidio, LLM) but exercising the real
# pre_classifier, prompt_builder, and policy_engine logic.

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

import pytest

import config  # noqa: E402


# ---------------------------------------------------------------------------
# Mock dataclass for LexicalResult (mirrors lexical_engine.LexicalResult)
# ---------------------------------------------------------------------------

@dataclass
class MockLexicalResult:
    """Mock LexicalResult for controlled routing tests."""
    tfidf_score: float = 0.0
    verdict: str = "PUBLIC"
    top_docs: list = field(default_factory=list)
    matched_terms: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_presidio_result(entity_types_with_values: list[dict] | None = None) -> dict:
    """
    Build a mock presidio_result dict.

    entity_types_with_values: list of dicts with 'entity_type' and optionally 'value'.
    If None, returns a result with no entities.
    """
    if entity_types_with_values is None:
        return {
            "entityCount": 0,
            "maskedText": "What is the weather like today?",
            "entities": [],
        }

    entities = []
    for i, et_dict in enumerate(entity_types_with_values):
        entities.append({
            "entity_type": et_dict["entity_type"],
            "value": et_dict.get("value", "REDACTED"),
            "score": et_dict.get("score", 0.99),
            "start": i * 10,
            "end": i * 10 + 8,
        })

    masked_parts = [f"<{e['entity_type']}>" for e in entities]
    masked_text = "Prompt with " + " and ".join(masked_parts)

    return {
        "entityCount": len(entities),
        "maskedText": masked_text,
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
    mock_result.top_chunks = [{"text": "chunk context", "score": semantic_score}]
    mock_result.source_docs = ["test.md"]
    mock_engine.search.return_value = mock_result
    mock_engine.available = True
    return mock_engine


def _run_full_pipeline(prompt: str, presidio_result: dict, verdict: str = "PUBLIC",
                       tfidf_score: float = 0.1, is_trivial: bool = False,
                       lexical_available: bool = True, semantic_available: bool = True,
                       semantic_score: float = 0.5, llm_eci_result: dict | None = None):
    """
    Run the full pipeline: pre_classify -> (optional LLM) -> policy decide.

    Mocks the lexical/semantic engines and is_trivial_prompt.
    When the pipeline routes to LLM, mocks classify_context with llm_eci_result.

    Returns (pre_result, policy_result, status) tuple.
    """
    import ai.pre_classifier as pre_classifier_module
    from policy_engine import decide as decide_policy

    mock_lexical = _make_mock_lexical_engine(verdict, tfidf_score)
    mock_semantic = _make_mock_semantic_engine(semantic_score)

    with patch.object(pre_classifier_module, '_lexical_available', lexical_available), \
         patch.object(pre_classifier_module, '_lexical_engine_instance', mock_lexical if lexical_available else None), \
         patch.object(pre_classifier_module, '_semantic_available', semantic_available), \
         patch.object(pre_classifier_module, '_semantic_engine_instance', mock_semantic if semantic_available else None), \
         patch.object(config, 'USE_LEGACY_SEARCH', False), \
         patch("ai.pre_classifier.is_trivial_prompt", return_value=is_trivial):
        pre_result = pre_classifier_module.pre_classify(prompt, presidio_result["maskedText"], presidio_result)

    # Determine ECI result
    if not pre_result["needs_llm"]:
        eci_raw = pre_result["pre_eci"]
    else:
        # When LLM is needed, use the provided mock ECI result or a default
        if llm_eci_result is not None:
            eci_raw = llm_eci_result
        else:
            # Default LLM response: enterprise context detected
            eci_raw = {
                "intent": "Other",
                "documentType": "Internal Documentation",
                "requiresEnterpriseKnowledge": True,
                "containsInternalArchitecture": True,
                "containsImplementationDetails": True,
                "containsSourceCode": False,
                "containsCustomerData": False,
                "containsSecrets": False,
                "impactsGDPR": False,
                "impactsPCIDSS": False,
                "impactsHIPAA": False,
                "impactsISO27001": True,
                "confidence": 0.92,
                "reasoning": ["Enterprise context confirmed by LLM"],
            }

    # Run policy engine
    detection = {
        "entityCount": presidio_result["entityCount"],
        "entityTypes": [e["entity_type"] for e in presidio_result["entities"]],
    }
    policy_result = decide_policy(detection, eci_raw)

    # Map policy decision to user-facing status (mirrors routes.py)
    DECISION_TO_STATUS = {
        "ALLOW": "SAFE",
        "WARN": "WARN",
        "MASK": "SANITIZE",
        "BLOCK": "BLOCK",
    }
    status = DECISION_TO_STATUS.get(policy_result["decision"], "SANITIZE")

    return pre_result, policy_result, status


# ===========================================================================
# Integration tests: end-to-end routing decisions
# ===========================================================================


class TestTrivialPromptRouting:
    """Test: trivial prompt with no entities skips LLM entirely."""

    def test_trivial_prompt_skips_llm(self):
        """
        A trivial prompt with no entities should:
        - Route via decision_path="trivial"
        - NOT require LLM (needs_llm=False)
        - Policy engine outputs ALLOW (status=SAFE)
        """
        presidio_result = _build_presidio_result(None)

        pre_result, policy_result, status = _run_full_pipeline(
            prompt="hello",
            presidio_result=presidio_result,
            is_trivial=True,
        )

        assert pre_result["decision_path"] == "trivial"
        assert pre_result["needs_llm"] is False
        assert status == "SAFE"
        assert policy_result["decision"] == "ALLOW"


class TestSecretsHardBlock:
    """Test: secrets detected produces hard_block and BLOCK policy."""

    def test_secrets_detected_hard_block(self):
        """
        A prompt with secret entities (GITHUB_TOKEN) should:
        - Route via decision_path="hard_block"
        - NOT require LLM (needs_llm=False)
        - Policy engine outputs BLOCK
        """
        presidio_result = _build_presidio_result([
            {"entity_type": "GITHUB_TOKEN", "value": "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        ])

        pre_result, policy_result, status = _run_full_pipeline(
            prompt="My token is ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            presidio_result=presidio_result,
        )

        assert pre_result["decision_path"] == "hard_block"
        assert pre_result["needs_llm"] is False
        assert status == "BLOCK"
        assert policy_result["decision"] == "BLOCK"

    def test_secrets_with_pii_still_hard_block(self):
        """
        Secrets always take priority over PII - should still hard_block.
        """
        presidio_result = _build_presidio_result([
            {"entity_type": "GITHUB_TOKEN", "value": "ghp_xxxx"},
            {"entity_type": "EMAIL_ADDRESS", "value": "user@example.com"},
        ])

        pre_result, policy_result, status = _run_full_pipeline(
            prompt="Token ghp_xxxx email user@example.com",
            presidio_result=presidio_result,
        )

        assert pre_result["decision_path"] == "hard_block"
        assert pre_result["needs_llm"] is False
        assert status == "BLOCK"


class TestPiiOnlyNoEnterprise:
    """Test: PII detected + lexical verdict PUBLIC routes to pii_only."""

    def test_pii_only_no_enterprise(self):
        """
        PII detected + lexical verdict PUBLIC should:
        - Route via decision_path="pii_only"
        - NOT require LLM (needs_llm=False)
        - Policy engine outputs MASK (status=SANITIZE)
        """
        presidio_result = _build_presidio_result([
            {"entity_type": "PERSON", "value": "John Smith"},
            {"entity_type": "EMAIL_ADDRESS", "value": "john@company.com"},
        ])

        pre_result, policy_result, status = _run_full_pipeline(
            prompt="Please contact John Smith at john@company.com",
            presidio_result=presidio_result,
            verdict="PUBLIC",
            tfidf_score=0.05,
        )

        assert pre_result["decision_path"] == "pii_only"
        assert pre_result["needs_llm"] is False
        # Policy should decide MASK or WARN for PII without enterprise context
        assert policy_result["decision"] in ("MASK", "WARN", "ALLOW")
        assert status in ("SAFE", "SANITIZE", "WARN")


class TestGeneralKnowledgePublic:
    """Test: No PII + lexical verdict PUBLIC routes to general_knowledge."""

    def test_general_knowledge_public(self):
        """
        No PII + lexical verdict PUBLIC should:
        - Route via decision_path="general_knowledge"
        - NOT require LLM (needs_llm=False)
        - Policy engine outputs ALLOW (status=SAFE)
        """
        presidio_result = _build_presidio_result(None)

        pre_result, policy_result, status = _run_full_pipeline(
            prompt="What is OAuth2?",
            presidio_result=presidio_result,
            verdict="PUBLIC",
            tfidf_score=0.08,
            is_trivial=False,
        )

        assert pre_result["decision_path"] == "general_knowledge"
        assert pre_result["needs_llm"] is False
        assert status == "SAFE"
        assert policy_result["decision"] == "ALLOW"


class TestEnterpriseLikelyNeedsReview:
    """
    Test: Lexical verdict ENTERPRISE_LIKELY routes to the LLM for review.

    Renamed from TestEnterpriseLikelyDetected. "Detected" described the
    behavior removed by specs/lexical-semantic-fix Task 2.1, where a TF-IDF
    threshold crossing was treated as a detection rather than as a lead.
    """

    def test_enterprise_likely_routes_to_llm_review(self):
        """
        Lexical verdict ENTERPRISE_LIKELY should:
        - Route via decision_path="enterprise_lexical_needs_review"
        - REQUIRE the LLM (needs_llm=True), carrying no pre-filled ECI
        - Let the LLM's verdict, not the lexical score, drive the policy outcome
        """
        presidio_result = _build_presidio_result(None)

        # The LLM is the reviewer here. Give it the answer a competent reviewer
        # would return for a public-knowledge prompt that merely shares
        # vocabulary with the corpus, so the test shows the review actually
        # governs the outcome.
        public_verdict_eci = {
            "intent": "Other",
            "documentType": "None",
            "requiresEnterpriseKnowledge": False,
            "containsInternalArchitecture": False,
            "containsImplementationDetails": False,
            "containsSourceCode": False,
            "containsCustomerData": False,
            "containsSecrets": False,
            "impactsGDPR": False,
            "impactsPCIDSS": False,
            "impactsHIPAA": False,
            "impactsISO27001": False,
            "confidence": 0.91,
            "reasoning": ["Generic protocol question, no enterprise specifics"],
        }

        pre_result, policy_result, status = _run_full_pipeline(
            prompt="In general terms, how does an OAuth 2.0 client_credentials grant work?",
            presidio_result=presidio_result,
            verdict="ENTERPRISE_LIKELY",
            tfidf_score=0.65,
            is_trivial=False,
            llm_eci_result=public_verdict_eci,
        )

        # WHY these expectations changed from enterprise_detected/needs_llm=False:
        # A TF-IDF score is a retrieval signal - vocabulary overlap with the
        # knowledge corpus - not a disclosure judgement. The corpus documents
        # OAuth 2.0 and GDPR, so generic public questions about them score
        # highly too: this exact prompt measured 0.7200, higher than every
        # expected-BLOCK case in the suite. Crossing the threshold may earn a
        # prompt an LLM review; it must not decide the outcome of that review.
        assert pre_result["decision_path"] == "enterprise_lexical_needs_review"
        assert pre_result["needs_llm"] is True

        # WHY pre_eci must be None: the removed branch returned a synthetic ECI
        # with containsInternalArchitecture=True at confidence=0.9, which
        # rules.json blocks on at eci_min_confidence=0.7. One threshold
        # crossing became a deterministic BLOCK that no reviewer saw.
        assert pre_result["pre_eci"] is None

        # And the consequence that matters end-to-end: with the reviewer saying
        # "public", the same prompt that used to hard-BLOCK now lands SAFE.
        # This is the assertion that inverts if Task 2.1 is reverted.
        assert policy_result["decision"] == "ALLOW"
        assert status == "SAFE"
        assert "block_internal_architecture_or_code" not in policy_result["matchedRules"]

    def test_enterprise_likely_still_blocks_when_llm_confirms(self):
        """
        The counterpart: routing to the LLM does not weaken enforcement. When
        the reviewer confirms internal architecture, the BLOCK still happens -
        it is now backed by a classification instead of by a score.
        """
        presidio_result = _build_presidio_result(None)

        pre_result, policy_result, status = _run_full_pipeline(
            prompt="How does the Mercury authorization pipeline call Orion Identity?",
            presidio_result=presidio_result,
            verdict="ENTERPRISE_LIKELY",
            tfidf_score=0.65,
            is_trivial=False,
            llm_eci_result={
                "intent": "Other",
                "documentType": "Internal Documentation",
                "requiresEnterpriseKnowledge": True,
                "containsInternalArchitecture": True,
                "containsImplementationDetails": True,
                "containsSourceCode": False,
                "containsCustomerData": False,
                "containsSecrets": False,
                "impactsGDPR": False,
                "impactsPCIDSS": False,
                "impactsHIPAA": False,
                "impactsISO27001": True,
                "confidence": 0.93,
                "reasoning": ["Names internal systems and their call path"],
            },
        )

        assert pre_result["decision_path"] == "enterprise_lexical_needs_review"
        assert pre_result["needs_llm"] is True
        assert policy_result["decision"] == "BLOCK"
        assert status == "BLOCK"


class TestTrueAmbiguityCallsLlm:
    """Test: Lexical verdict AMBIGUOUS + hybrid score in gray zone routes to LLM."""

    def test_true_ambiguity_calls_llm(self):
        """
        Lexical verdict AMBIGUOUS + hybrid score in gray zone should:
        - Route via decision_path="true_ambiguity"
        - Require LLM (needs_llm=True)
        - LLM provides ECI result, policy engine uses it for final decision
        """
        presidio_result = _build_presidio_result(None)

        # Hybrid score = 0.4 * 0.30 + 0.6 * 0.50 = 0.12 + 0.30 = 0.42
        # This is between HYBRID_PUBLIC_THRESHOLD (0.30) and HYBRID_ENTERPRISE_THRESHOLD (0.55)
        # -> true_ambiguity
        pre_result, policy_result, status = _run_full_pipeline(
            prompt="Explain the authentication flow for our service",
            presidio_result=presidio_result,
            verdict="AMBIGUOUS",
            tfidf_score=0.30,
            is_trivial=False,
            semantic_score=0.50,
            llm_eci_result={
                "intent": "Other",
                "documentType": "Internal Documentation",
                "requiresEnterpriseKnowledge": True,
                "containsInternalArchitecture": True,
                "containsImplementationDetails": True,
                "containsSourceCode": False,
                "containsCustomerData": False,
                "containsSecrets": False,
                "impactsGDPR": False,
                "impactsPCIDSS": False,
                "impactsHIPAA": False,
                "impactsISO27001": True,
                "confidence": 0.92,
                "reasoning": ["Enterprise context confirmed by LLM classification"],
            },
        )

        assert pre_result["decision_path"] == "true_ambiguity"
        assert pre_result["needs_llm"] is True
        assert pre_result["hybrid_score"] is not None
        # Hybrid score should be in the gray zone [0.30, 0.55)
        assert 0.30 <= pre_result["hybrid_score"] < 0.55, (
            f"Expected hybrid_score in gray zone [0.30, 0.55), got {pre_result['hybrid_score']}"
        )
        # LLM said enterprise -> policy should restrict
        assert policy_result["decision"] in ("BLOCK", "WARN", "MASK")
        assert status in ("BLOCK", "SANITIZE", "WARN")

    def test_ambiguous_below_public_threshold_routes_to_llm_review(self):
        """
        A LOW hybrid score no longer skips the LLM at the configured default.

        Renamed from test_ambiguous_below_public_threshold_skips_llm, which
        asserted decision_path == "semantic_confirmed_public" and
        needs_llm is False. That assertion encoded the behavior removed by
        specs/lexical-semantic-fix Task 8.2, which set the default
        HYBRID_PUBLIC_THRESHOLD to 0.0. Hybrid scores are >= 0 by construction,
        so `hybrid_score < 0.0` is never true and the branch no longer fires.

        ── Why the branch was disabled ──────────────────────────────────────
        semantic_confirmed_public was the last path that skipped the LLM purely
        on a retrieval score, and the only tier-2 path that skipped it at all.
        Tasks 2.1 and 3.3 removed its two mirror images - the ones asserting
        ENTERPRISE from a HIGH score - because TF-IDF and embedding similarity
        are retrieval signals, not disclosure judgements. This branch made the
        same category error in the safe direction: it concluded "this prompt
        discloses nothing" from "this prompt does not resemble the corpus".

        It survived those tasks only because it was unfalsifiable. Just 3 of the
        original 15 suite cases reached tier 2 and all 3 were expected-ALLOW, so
        no labelled case could contradict it. Task 8.1 grew the suite to 76
        cases, 38 of which reach tier 2, 12 of them expected-BLOCK. Measured on
        that suite, the hybrid score's ability to tell expected-BLOCK from
        expected-ALLOW among tier-2 cases is indistinguishable from chance:
        AUC 0.4872 over all labels, 0.5399 over the machine-generated subset,
        and undefined on the human-authored baseline because no human-authored
        BLOCK case reaches tier 2 at all. The semantic component alone scores
        0.3782, slightly worse than a coin flip.

        At the old 0.30 the branch fired 5 times in 76, and 2 of those 5 were
        expected-BLOCK prompts proposing to hand data to an outsider (#75, a
        conference bridge passcode; #76, interchange margin figures). Both score
        low only because they use almost no corpus vocabulary. A no-LLM skip is
        unrecoverable - nothing downstream re-examines the prompt.

        ── What still covers the branch ─────────────────────────────────────
        The threshold remains configurable, and setting
        PROMPTSHIELD_HYBRID_PUBLIC_THRESHOLD to a positive value restores the
        old routing. tests/test_hybrid_scoring.py's
        test_hybrid_routing_with_configurable_thresholds generates
        public_threshold over [0.01, 0.99] and asserts semantic_confirmed_public
        below it, so the re-enabled arithmetic stays covered there (against a
        pure mirror of the branch, not pre_classify itself).

        What this test now asserts is the deployed default: a low hybrid score
        earns a review rather than a verdict, and the reviewer's answer governs
        the outcome. The prompt below is genuinely public, the mocked reviewer
        says so, and the result is still SAFE - reached by review instead of by
        assertion.
        """
        presidio_result = _build_presidio_result(None)

        public_verdict_eci = {
            "intent": "Other",
            "documentType": "None",
            "requiresEnterpriseKnowledge": False,
            "containsInternalArchitecture": False,
            "containsImplementationDetails": False,
            "containsSourceCode": False,
            "containsCustomerData": False,
            "containsSecrets": False,
            "impactsGDPR": False,
            "impactsPCIDSS": False,
            "impactsHIPAA": False,
            "impactsISO27001": False,
            "confidence": 0.95,
            "reasoning": ["General technical question, no enterprise context"],
        }

        # Hybrid score = 0.4 * 0.10 + 0.6 * 0.20 = 0.04 + 0.12 = 0.16.
        # Below the OLD 0.30, which is the point: at the current default of 0.0
        # there is no low-score skip, so this lands in the gray zone instead.
        pre_result, policy_result, status = _run_full_pipeline(
            prompt="What is a database index?",
            presidio_result=presidio_result,
            verdict="AMBIGUOUS",
            tfidf_score=0.10,
            is_trivial=False,
            semantic_score=0.20,
            llm_eci_result=public_verdict_eci,
        )

        assert pre_result["decision_path"] == "true_ambiguity"
        assert pre_result["needs_llm"] is True
        assert pre_result["hybrid_score"] == pytest.approx(0.16)
        # The pre-classifier must not have pre-empted the review with a verdict.
        assert pre_result["pre_eci"] is None
        # Retrieval evidence is still carried forward for the reviewer and the
        # audit trail, even though it no longer decides anything.
        assert pre_result["semantic_result"] is not None
        # Reviewer says public, so the outcome is SAFE - by review, not by score.
        assert policy_result["decision"] == "ALLOW"
        assert status == "SAFE"

    def test_ambiguous_above_enterprise_threshold_routes_to_llm_review(self):
        """
        If AMBIGUOUS verdict but hybrid score >= HYBRID_ENTERPRISE_THRESHOLD,
        route to enterprise_hybrid_needs_review and let the LLM decide.

        Renamed from test_ambiguous_above_enterprise_threshold_skips_llm. The
        old name described the behavior removed by specs/lexical-semantic-fix
        Task 3.3 and had become a misnomer.
        """
        presidio_result = _build_presidio_result(None)

        # Hybrid score = 0.4 * 0.80 + 0.6 * 0.85 = 0.32 + 0.51 = 0.83
        # Above HYBRID_ENTERPRISE_THRESHOLD (0.55) -> enterprise_hybrid_needs_review
        #
        # The reviewer is given the answer a competent one would return for a
        # question that is merely ABOUT a documented topic, so the test shows
        # the review actually governs the outcome rather than the score.
        public_verdict_eci = {
            "intent": "Other",
            "documentType": "None",
            "requiresEnterpriseKnowledge": False,
            "containsInternalArchitecture": False,
            "containsImplementationDetails": False,
            "containsSourceCode": False,
            "containsCustomerData": False,
            "containsSecrets": False,
            "impactsGDPR": False,
            "impactsPCIDSS": False,
            "impactsHIPAA": False,
            "impactsISO27001": False,
            "confidence": 0.90,
            "reasoning": ["Conceptual policy question, no internal specifics disclosed"],
        }

        pre_result, policy_result, status = _run_full_pipeline(
            prompt="What are our three enterprise data classification levels?",
            presidio_result=presidio_result,
            verdict="AMBIGUOUS",
            tfidf_score=0.80,
            is_trivial=False,
            semantic_score=0.85,
            llm_eci_result=public_verdict_eci,
        )

        # WHY these expectations changed from semantic_confirmed_enterprise /
        # needs_llm=False: embedding similarity is a retrieval signal, exactly
        # as TF-IDF is. A high cosine score against a corpus document means the
        # prompt is ABOUT a documented topic, which is not evidence that
        # answering it discloses anything. Two retrieval signals agreeing makes
        # the retrieval more confident, not the disclosure judgement more valid.
        # Measured: suite case #10 (expected ALLOW / WARN) hit hybrid=0.6846 and
        # was deterministically BLOCKed at riskScore=54 the first time this path
        # was ever reachable.
        assert pre_result["decision_path"] == "enterprise_hybrid_needs_review"
        assert pre_result["needs_llm"] is True

        # WHY pre_eci must be None: the removed branch handed the policy engine
        # a synthetic ECI from _build_enterprise_eci() with
        # containsInternalArchitecture=True at confidence=0.9, which rules.json
        # blocks on at eci_min_confidence=0.7. Since Task 3.3 that builder no
        # longer exists.
        assert pre_result["pre_eci"] is None

        # The evidence is still carried forward for the LLM and the audit trail.
        assert pre_result["hybrid_score"] is not None
        assert pre_result["hybrid_score"] >= 0.55
        assert pre_result["semantic_result"] is not None
        assert pre_result["lexical_result"] is not None

        # The consequence that matters end-to-end, and the assertion that
        # inverts if Task 3.3 is reverted.
        assert policy_result["decision"] == "ALLOW"
        assert status == "SAFE"
        assert "block_internal_architecture_or_code" not in policy_result["matchedRules"]

    def test_hybrid_enterprise_still_blocks_when_llm_confirms(self):
        """
        The counterpart: routing to the LLM does not weaken enforcement. When
        the reviewer confirms internal architecture on a high-hybrid prompt, the
        BLOCK still happens - now backed by a classification, not by a score.
        """
        presidio_result = _build_presidio_result(None)

        pre_result, policy_result, status = _run_full_pipeline(
            prompt="Walk through how Token Vault detokenization is wired to Orion Identity internally.",
            presidio_result=presidio_result,
            verdict="AMBIGUOUS",
            tfidf_score=0.80,
            is_trivial=False,
            semantic_score=0.85,
            llm_eci_result={
                "intent": "Other",
                "documentType": "Internal Documentation",
                "requiresEnterpriseKnowledge": True,
                "containsInternalArchitecture": True,
                "containsImplementationDetails": True,
                "containsSourceCode": False,
                "containsCustomerData": False,
                "containsSecrets": False,
                "impactsGDPR": False,
                "impactsPCIDSS": False,
                "impactsHIPAA": False,
                "impactsISO27001": True,
                "confidence": 0.93,
                "reasoning": ["Requests the internal wiring between two named systems"],
            },
        )

        assert pre_result["decision_path"] == "enterprise_hybrid_needs_review"
        assert pre_result["needs_llm"] is True
        assert policy_result["decision"] == "BLOCK"
        assert status == "BLOCK"


class TestGracefulDegradation:
    """Test graceful degradation when engines are unavailable."""

    def test_graceful_degradation_lexical_unavailable(self):
        """
        When LexicalEngine is unavailable:
        - Should route via decision_path="engine_degraded"
        - Should still require LLM (needs_llm=True) as fallback
        - LLM response drives final policy decision
        """
        presidio_result = _build_presidio_result(None)

        pre_result, policy_result, status = _run_full_pipeline(
            prompt="Explain our internal deployment process",
            presidio_result=presidio_result,
            verdict="PUBLIC",  # won't matter since lexical is unavailable
            tfidf_score=0.0,
            is_trivial=False,
            lexical_available=False,
            llm_eci_result={
                "intent": "Other",
                "documentType": "Internal Documentation",
                "requiresEnterpriseKnowledge": True,
                "containsInternalArchitecture": True,
                "containsImplementationDetails": False,
                "containsSourceCode": False,
                "containsCustomerData": False,
                "containsSecrets": False,
                "impactsGDPR": False,
                "impactsPCIDSS": False,
                "impactsHIPAA": False,
                "impactsISO27001": True,
                "confidence": 0.88,
                "reasoning": ["Classified by LLM after lexical engine degradation"],
            },
        )

        assert pre_result["decision_path"] == "engine_degraded"
        assert pre_result["needs_llm"] is True
        # LLM classifies as enterprise -> policy restricts
        assert policy_result["decision"] in ("BLOCK", "WARN", "MASK")

    def test_graceful_degradation_semantic_unavailable(self):
        """
        When SemanticEngine is unavailable and lexical returns AMBIGUOUS:
        - Should route via decision_path="true_ambiguity"
        - Should require LLM (needs_llm=True)
        - LLM response drives final policy decision
        """
        presidio_result = _build_presidio_result(None)

        pre_result, policy_result, status = _run_full_pipeline(
            prompt="How does the authentication system handle refresh tokens?",
            presidio_result=presidio_result,
            verdict="AMBIGUOUS",
            tfidf_score=0.35,
            is_trivial=False,
            semantic_available=False,
            llm_eci_result={
                "intent": "Other",
                "documentType": "Internal Documentation",
                "requiresEnterpriseKnowledge": True,
                "containsInternalArchitecture": False,
                "containsImplementationDetails": True,
                "containsSourceCode": False,
                "containsCustomerData": False,
                "containsSecrets": False,
                "impactsGDPR": False,
                "impactsPCIDSS": False,
                "impactsHIPAA": False,
                "impactsISO27001": False,
                "confidence": 0.85,
                "reasoning": ["Classified by LLM after semantic engine unavailable"],
            },
        )

        assert pre_result["decision_path"] == "true_ambiguity"
        assert pre_result["needs_llm"] is True
        # Semantic result should be None since semantic engine is unavailable
        assert pre_result["semantic_result"] is None
        assert pre_result["hybrid_score"] is None

    def test_trivial_prompt_still_works_when_engines_unavailable(self):
        """
        Even when both engines are unavailable, trivial prompts should
        still be handled correctly (trivial path doesn't need engines).
        """
        presidio_result = _build_presidio_result(None)

        pre_result, policy_result, status = _run_full_pipeline(
            prompt="hello",
            presidio_result=presidio_result,
            is_trivial=True,
            lexical_available=False,
            semantic_available=False,
        )

        assert pre_result["decision_path"] == "trivial"
        assert pre_result["needs_llm"] is False
        assert status == "SAFE"

    def test_secrets_still_blocked_when_engines_unavailable(self):
        """
        Even when both engines are unavailable, secrets detection should
        still produce hard_block (secrets path doesn't need engines).
        """
        presidio_result = _build_presidio_result([
            {"entity_type": "AWS_ACCESS_KEY", "value": "AKIAIOSFODNN7EXAMPLE"},
        ])

        pre_result, policy_result, status = _run_full_pipeline(
            prompt="My AWS key is AKIAIOSFODNN7EXAMPLE",
            presidio_result=presidio_result,
            lexical_available=False,
            semantic_available=False,
        )

        assert pre_result["decision_path"] == "hard_block"
        assert pre_result["needs_llm"] is False
        assert status == "BLOCK"


class TestResponseStructure:
    """Test that all decision paths produce valid response structures."""

    @pytest.mark.parametrize("path_config", [
        {
            "name": "trivial",
            "is_trivial": True,
            "entities": None,
            "verdict": "PUBLIC",
            "tfidf": 0.0,
        },
        {
            "name": "hard_block",
            "is_trivial": False,
            "entities": [{"entity_type": "JWT_TOKEN", "value": "eyJhbGci..."}],
            "verdict": "PUBLIC",
            "tfidf": 0.0,
        },
        {
            "name": "pii_only",
            "is_trivial": False,
            "entities": [{"entity_type": "PHONE_NUMBER", "value": "+1234567890"}],
            "verdict": "PUBLIC",
            "tfidf": 0.08,
        },
        {
            "name": "general_knowledge",
            "is_trivial": False,
            "entities": None,
            "verdict": "PUBLIC",
            "tfidf": 0.05,
        },
        {
            # Renamed from "enterprise_detected": since Task 2.1 this case
            # routes to the LLM rather than skipping it. The response shape is
            # asserted either way, which is the point of this test.
            "name": "enterprise_lexical_needs_review",
            "is_trivial": False,
            "entities": None,
            "verdict": "ENTERPRISE_LIKELY",
            "tfidf": 0.70,
        },
    ])
    def test_all_decision_paths_produce_valid_structure(self, path_config):
        """
        Every decision path should produce a valid response with all required
        keys and sensible values, whether it skips the LLM or routes to it.
        """
        presidio_result = _build_presidio_result(path_config["entities"])

        pre_result, policy_result, status = _run_full_pipeline(
            prompt="test prompt",
            presidio_result=presidio_result,
            verdict=path_config["verdict"],
            tfidf_score=path_config["tfidf"],
            is_trivial=path_config["is_trivial"],
        )

        # Pre-classifier result structure
        assert "needs_llm" in pre_result
        assert "reason" in pre_result
        assert "decision_path" in pre_result
        assert "pre_eci" in pre_result
        assert "knowledge_hits" in pre_result
        assert "lexical_result" in pre_result
        assert "semantic_result" in pre_result
        assert "hybrid_score" in pre_result
        assert isinstance(pre_result["needs_llm"], bool)
        assert isinstance(pre_result["reason"], str)
        assert isinstance(pre_result["decision_path"], str)

        # Policy result structure
        assert "decision" in policy_result
        assert "explanation" in policy_result
        assert "riskScore" in policy_result
        assert "matchedRules" in policy_result
        assert policy_result["decision"] in ("ALLOW", "WARN", "MASK", "BLOCK")
        assert isinstance(policy_result["riskScore"], int)
        assert isinstance(policy_result["matchedRules"], list)

        # Status mapping is valid
        assert status in ("SAFE", "SANITIZE", "WARN", "BLOCK")
