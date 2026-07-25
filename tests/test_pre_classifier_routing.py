# Feature: lexical-semantic-upgrade, Property 6: Pre-Classifier Priority Routing
# **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**
#
# Property 6: For any combination of (secrets, PII, lexical_verdict), the
# Pre-Classifier SHALL route according to strict priority order:
#   1. Secrets detected -> hard_block (always, regardless of other signals)
#   2. PII + PUBLIC verdict -> pii_only
#   3. PUBLIC verdict, no PII -> general_knowledge
#   4. ENTERPRISE_LIKELY verdict -> enterprise_detected
#   5. AMBIGUOUS verdict -> semantic engine invoked (needs_llm depends on hybrid)

import os
import sys

_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "backend"))
_AI_DIR = os.path.join(_BACKEND_DIR, "ai")
for _d in (_BACKEND_DIR, _AI_DIR):
    if _d not in sys.path:
        sys.path.insert(0, _d)

from dataclasses import dataclass, field
from unittest.mock import patch, MagicMock

from hypothesis import given, settings, assume
from hypothesis import strategies as st

import config  # noqa: E402


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
def test_enterprise_likely_produces_enterprise_detected(entities, tfidf_score, prompt):
    """
    Property 6d: ENTERPRISE_LIKELY verdict -> enterprise_detected.

    When the lexical engine returns an ENTERPRISE_LIKELY verdict, the
    pre-classifier SHALL return decision_path='enterprise_detected' with
    needs_llm=False, regardless of PII presence.
    """
    presidio_result = _build_presidio_result(entities)

    result = _call_pre_classify(prompt, presidio_result, "ENTERPRISE_LIKELY", tfidf_score)

    assert result["decision_path"] == "enterprise_detected", (
        f"Expected enterprise_detected when verdict=ENTERPRISE_LIKELY, "
        f"but got decision_path={result['decision_path']!r}"
    )
    assert result["needs_llm"] is False, (
        f"Expected needs_llm=False for enterprise_detected, got {result['needs_llm']}"
    )


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
    semantic_confirmed_public, semantic_confirmed_enterprise, or true_ambiguity
    depending on the hybrid score.
    """
    presidio_result = _build_presidio_result(entities)

    result = _call_pre_classify(
        prompt, presidio_result, "AMBIGUOUS", tfidf_score,
        semantic_available=True, semantic_score=0.5,
    )

    # When AMBIGUOUS, the decision should be one of the tier-2 paths
    valid_ambiguous_paths = {
        "semantic_confirmed_public",
        "semantic_confirmed_enterprise",
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
