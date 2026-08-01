# test_presidio_product_allowlist.py
# Feature: lexical-semantic-fix, task 5 (Findings 7)
#
# Guards the product-name PERSON allowlist added to presidio_engine.py.
#
# The false positive being fixed is cosmetic: spaCy's NER labels the platform
# name 'Token Vault' PERSON at score 0.8500. The failure mode of the FIX is not
# cosmetic - every name the allowlist wrongly contains is a real person Presidio
# stops masking. So the bulk of this file is the negative direction: real names,
# including names that collide with corpus vocabulary, must still be detected
# and masked, and the derived allowlist must not silently grow.

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from presidio.presidio_engine import analyze_text
from presidio.product_names import is_product_name, load_product_names


# The six platform names the corpus actually documents - the "Major Enterprise
# Applications" table in knowledge/architecture/application-landscape.md. Kept
# here as a literal so a change to the extractor that widens the derived set
# fails loudly instead of quietly suppressing more PERSON detections.
EXPECTED_ALLOWLIST = {
    "Atlas Analytics",
    "Merchant Registry",
    "Mercury Payments",
    "Nexus Portal",
    "Orion Identity",
    "Token Vault",
}

# Suite case #4 (tests/PromptShield_TestSuite.xlsx, row 5), verbatim.
CASE_4 = (
    "Draft a detailed architecture doc explaining exactly how Mercury Payments' "
    "authorization pipeline routes a transaction through Orion Identity, Token "
    "Vault, and Merchant Registry \u2014 including our internal service topology "
    "and failover design \u2014 so I can hand it to an external contractor."
)

REAL_NAME_CONTROLS = [
    ("Rajesh Kumar", "Please email Rajesh Kumar about the merchant dispute."),
    ("Priya Sharma", "Escalate the dispute to Priya Sharma before end of day."),
    ("Sarah Johnson", "The reviewer is Sarah Johnson from Internal Audit."),
    # Names that collide with a word in the allowlist. Full-span equality is
    # what keeps these detected; substring containment would suppress all three.
    ("Mercury Sharma", "Assign the ticket to Mercury Sharma."),
    ("Vault Ramachandran", "Please ask Vault Ramachandran to sign off."),
    ("Atlas Fernandes", "Atlas Fernandes approved the change request."),
    # A real name sharing a sentence with the product name that used to misfire.
    ("Rajesh Kumar", "Rajesh Kumar owns the Token Vault rotation runbook."),
]


# ---------------------------------------------------------------------------
# The allowlist itself (task 5.2)
# ---------------------------------------------------------------------------

def test_allowlist_is_derived_from_the_corpus_and_enumerable():
    """The derived set is exactly the corpus's platform names, nothing more."""
    assert set(load_product_names(force_reload=True)) == EXPECTED_ALLOWLIST


@pytest.mark.parametrize("not_a_product", [
    # Document titles from knowledge/architecture/ - documents, not platforms.
    "Application Landscape", "Enterprise Architecture", "System Integrations",
    "Deployment Architecture",
    # Bodies and teams that appear in product front matter and prose. These are
    # what a prose-scanning extractor would pull in.
    "Change Advisory Board", "Security Governance Council", "Payments Engineering",
    "Information Security", "Vault Operations",
    # Single corpus words: rejected on purpose, they are the ones likely to
    # collide with a real given name or surname.
    "Token", "Vault", "Mercury", "Atlas", "Orion", "Nexus",
])
def test_allowlist_excludes_non_platform_names(not_a_product):
    assert not is_product_name(not_a_product)


@pytest.mark.parametrize("variant", [
    "Token Vault", "token vault", "TOKEN VAULT", "  Token Vault  ",
    "Token   Vault", "Token\nVault", "Token Vault's", "Token Vault\u2019s",
    "Token Vault,", "(Token Vault)",
])
def test_matching_is_case_and_whitespace_insensitive(variant):
    """A span can arrive line-wrapped, punctuated or possessive - all one name."""
    assert is_product_name(variant)


@pytest.mark.parametrize("near_miss", [
    "Token Vault Team",   # extra word: a different thing
    "Vault Token",        # reordered: a different thing
    "TokenVault",         # no separator: not the corpus name
    "",
])
def test_matching_requires_full_span_equality(near_miss):
    assert not is_product_name(near_miss)


# ---------------------------------------------------------------------------
# Engine behaviour (task 5.1)
# ---------------------------------------------------------------------------

def test_case_4_product_name_is_not_reported_as_a_person():
    """Suite case #4 end-to-end: no PERSON issue, and nothing masked for it."""
    result = analyze_text(CASE_4)

    persons = [e for e in result["entities"] if e["entity_type"] == "PERSON"]
    assert persons == []
    assert "<PERSON>" not in result["maskedText"]
    assert "Token Vault" in result["maskedText"]


def test_masked_text_and_reported_entities_stay_consistent():
    """
    Every entity in the reported list must have a placeholder in the masked
    text, and the masked text must not contain a placeholder for a suppressed
    detection. This is what the filter's placement before _resolve_overlaps()
    buys: the issues panel and the sanitized prompt are built from one set.
    """
    result = analyze_text(CASE_4)
    placeholders = set(re.findall(r"<([A-Z_]+)>", result["maskedText"]))
    assert placeholders == {e["entity_type"] for e in result["entities"]}
    assert result["entityCount"] == len(result["entities"])


@pytest.mark.parametrize("name,text", REAL_NAME_CONTROLS)
def test_real_names_are_still_detected_and_masked(name, text):
    """The regression that matters: a false negative here is unmasked PII."""
    result = analyze_text(text)

    persons = [e for e in result["entities"] if e["entity_type"] == "PERSON"]
    assert name in [p["value"] for p in persons], (
        f"{name!r} was not detected as PERSON; entities={result['entities']}"
    )
    assert name not in result["maskedText"]
    assert "<PERSON>" in result["maskedText"]


@pytest.mark.parametrize("expected_type,text", [
    ("AWS_ACCESS_KEY",
     "I need help fixing our CI/CD pipeline for the Token Vault key rotation job "
     "\u2014 here's our deploy key: AKIAIOSFODNN7EXAMPLE. The rotation step keeps "
     "timing out."),
    ("GITHUB_TOKEN",
     "Here's our GitHub deploy token for the Token Vault release pipeline \u2014 "
     "ghp_123456789012345678901234567890123456 \u2014 please rotate it."),
])
def test_only_person_detections_are_suppressed(expected_type, text):
    """A product name in the prompt must not silence a credential recognizer."""
    result = analyze_text(text)
    types = {e["entity_type"] for e in result["entities"]}
    assert expected_type in types
    assert f"<{expected_type}>" in result["maskedText"]


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------

# Two or three capitalised words, the shape spaCy mistakes for a person name.
_capitalised_word = st.from_regex(r"[A-Z][a-z]{1,10}", fullmatch=True)
_person_like_name = st.lists(_capitalised_word, min_size=2, max_size=3).map(" ".join)


@given(name=_person_like_name)
@settings(max_examples=300)
def test_property_only_exact_corpus_names_are_suppressed(name):
    """
    No person-shaped name is suppressed unless it IS one of the corpus platform
    names. Bounds the allowlist's blast radius to its enumerated contents: an
    over-broad matcher (substring, per-word, prefix) fails this immediately.
    """
    allowlist = {n.casefold() for n in load_product_names()}
    assert is_product_name(name) == (name.casefold() in allowlist)


@given(
    pad_left=st.text(alphabet=" \t\n", max_size=3),
    pad_right=st.text(alphabet=" \t\n", max_size=3),
    inner=st.text(alphabet=" \t\n", min_size=1, max_size=3),
    upper_mask=st.lists(st.booleans(), min_size=1, max_size=40),
    suffix=st.sampled_from(["", ".", ",", "'s", "\u2019s", ")"]),
)
@settings(max_examples=300)
def test_property_recognition_survives_span_formatting(
    pad_left, pad_right, inner, upper_mask, suffix
):
    """
    A corpus name stays recognised however the detected span is cased, padded,
    internally re-whitespaced, punctuated or made possessive. Presidio spans
    come straight out of the source text, so all of these occur in real prompts.
    """
    for canonical in load_product_names():
        head, _, tail = canonical.partition(" ")
        respaced = f"{head}{inner}{tail}" if tail else canonical
        cased = "".join(
            c.upper() if upper_mask[i % len(upper_mask)] else c.lower()
            for i, c in enumerate(respaced)
        )
        span = f"{pad_left}{cased}{suffix}{pad_right}"
        assert is_product_name(span), f"{span!r} should match {canonical!r}"
