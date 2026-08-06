# Regression tests against the REAL knowledge base (not synthetic corpora).
#
# Guards two related failure modes discovered while tuning IDF weighting
# in the lexical engine:
#   1. Homonym collisions: a word that coincides with an internal
#      product/service name (e.g. "Mercury", "Orion", "Atlas") should not
#      falsely flag an unrelated public-knowledge question just because the
#      word also happens to be enterprise vocabulary.
#   2. Silent false negatives: a short, genuinely enterprise-specific
#      question built mostly from the organization's own core/ubiquitous
#      terms (e.g. "our identity service") must not be waved through as
#      PUBLIC with zero scrutiny just because those terms are common across
#      the knowledge base - high document frequency here means "central to
#      the business", not "generic filler word".

import os
import sys

_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "backend"))
_AI_DIR = os.path.join(_BACKEND_DIR, "ai")
for _d in (_BACKEND_DIR, _AI_DIR):
    if _d not in sys.path:
        sys.path.insert(0, _d)

import pytest

from context_loader import load_knowledge_base  # noqa: E402
from lexical_engine import LexicalEngine  # noqa: E402
from pre_classifier import pre_classify  # noqa: E402


@pytest.fixture(scope="module")
def real_engine():
    docs = load_knowledge_base()
    return LexicalEngine(docs)


def _no_entity_presidio_result(prompt: str) -> dict:
    return {"entityCount": 0, "maskedText": prompt, "entities": []}


# ---------------------------------------------------------------------------
# Homonym collisions: same word, unrelated public-knowledge meaning
# ---------------------------------------------------------------------------

HOMONYM_PUBLIC_PROMPTS = [
    "Tell me about planet Mercury.",
    "Tell me about the Orion constellation.",
    "What is the mythology behind Atlas holding up the sky?",
    "What is a supernova?",
]


@pytest.mark.parametrize("prompt", HOMONYM_PUBLIC_PROMPTS)
def test_homonym_prompts_score_public(real_engine, prompt):
    """
    A prompt using a word that coincides with an internal product/service
    name (Mercury, Orion, Atlas, Nova) - but in an unrelated public-knowledge
    sense - must not be flagged as enterprise-relevant.
    """
    result = real_engine.score(prompt)
    assert result.verdict == "PUBLIC", (
        f"Expected PUBLIC for homonym prompt {prompt!r}, "
        f"got verdict={result.verdict} (score={result.tfidf_score})"
    )


@pytest.mark.parametrize("prompt", HOMONYM_PUBLIC_PROMPTS)
def test_homonym_prompts_skip_llm_with_no_scrutiny_flags(prompt):
    """
    Same prompts, through the full pre-classifier: should resolve as
    general_knowledge (ALLOW-equivalent), not get flagged as enterprise.
    """
    result = pre_classify(prompt, prompt, _no_entity_presidio_result(prompt))
    assert result["decision_path"] == "general_knowledge", (
        f"Expected general_knowledge for homonym prompt {prompt!r}, "
        f"got decision_path={result['decision_path']!r}"
    )


# ---------------------------------------------------------------------------
# Silent false negatives: short prompts built from ubiquitous enterprise terms
# ---------------------------------------------------------------------------

SHORT_ENTERPRISE_PROMPTS = [
    "What does our identity service do?",
    "What is Orion?",
    "Describe our payment service.",
]


@pytest.mark.parametrize("prompt", SHORT_ENTERPRISE_PROMPTS)
def test_short_enterprise_prompts_are_not_silently_public(real_engine, prompt):
    """
    A short prompt relying mainly on the organization's own core/ubiquitous
    terms (identity, payment, Orion) must not score as pure PUBLIC just
    because those terms are common across the knowledge base.
    """
    result = real_engine.score(prompt)
    assert result.verdict != "PUBLIC", (
        f"Expected AMBIGUOUS or ENTERPRISE_LIKELY for {prompt!r}, "
        f"got verdict=PUBLIC (score={result.tfidf_score}) - this term was "
        "silently zeroed out and would bypass all scrutiny"
    )


@pytest.mark.parametrize("prompt", SHORT_ENTERPRISE_PROMPTS)
def test_short_enterprise_prompts_do_not_skip_via_general_knowledge(prompt):
    """
    Same prompts, through the full pre-classifier: must not take the
    general_knowledge (ALLOW-equivalent, zero-scrutiny) fast path.
    """
    result = pre_classify(prompt, prompt, _no_entity_presidio_result(prompt))
    assert result["decision_path"] != "general_knowledge", (
        f"Expected {prompt!r} to receive scrutiny (LLM or a deterministic "
        f"enterprise path), but it took the general_knowledge free pass "
        f"(decision_path={result['decision_path']!r})"
    )
