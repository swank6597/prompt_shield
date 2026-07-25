# Feature: lexical-semantic-upgrade, Property 1: IDF Correctness with High-Frequency Dampening
# **Validates: Requirements 1.2, 1.3**
#
# Property 1: For any corpus of documents and for any token present in the
# corpus, the computed IDF weight SHALL equal log(N / df(t)) when the token
# appears in 60% or fewer of the documents, and SHALL be near-zero (< 0.01)
# when the token appears in more than 60% of documents.

import math
import os
import sys

# Path setup so we can import from backend/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend", "ai"))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from ai.lexical_engine import LexicalEngine, LexicalConfig


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Generate valid tokens: start with a letter, followed by letters/digits/hyphens/underscores,
# total length > 2 (matching the engine's tokenizer filter)
valid_token_st = st.from_regex(r"[a-z][a-z0-9_-]{2,8}", fullmatch=True)

# Generate a document dict with content composed of known tokens
def document_from_tokens(tokens: list[str]) -> dict:
    """Create a document dict from a list of tokens."""
    return {
        "path": "test/path.md",
        "filename": "path.md",
        "category": "test",
        "content": " ".join(tokens),
    }


# Strategy: generate a corpus of 1-100 documents, each containing 1-20 tokens
# drawn from a shared vocabulary of 2-15 unique tokens
@st.composite
def corpus_strategy(draw):
    """Generate a random corpus with known token distributions."""
    # Generate a vocabulary of 2-15 unique tokens
    vocab_size = draw(st.integers(min_value=2, max_value=15))
    vocab = draw(
        st.lists(valid_token_st, min_size=vocab_size, max_size=vocab_size, unique=True)
    )

    # Generate 1-100 documents, each picking 1-20 tokens from the vocabulary
    num_docs = draw(st.integers(min_value=1, max_value=100))
    documents = []
    for _ in range(num_docs):
        # Each document has 1-20 tokens drawn from the vocabulary (with repetition)
        doc_tokens = draw(
            st.lists(st.sampled_from(vocab), min_size=1, max_size=20)
        )
        documents.append(document_from_tokens(doc_tokens))

    return documents


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------

@given(documents=corpus_strategy())
@settings(max_examples=200)
def test_idf_correctness_with_high_frequency_dampening(documents):
    """
    Property 1: IDF Correctness with High-Frequency Dampening.

    For every token in the IDF cache:
    - If df/N <= 0.60: IDF == log(N / df) (within floating-point tolerance)
    - If df/N > 0.60: IDF < 0.01
    """
    config = LexicalConfig()
    config.high_df_cutoff = 0.60

    engine = LexicalEngine(documents, config=config)

    N = len(documents)
    assume(N > 0)

    for token, idf_value in engine.idf_cache.items():
        # Get the document frequency from the inverted index
        df = engine.inverted_index[token]["df"]
        ratio = df / N

        if ratio > config.high_df_cutoff:
            # High-frequency dampening: must be near-zero
            assert idf_value < 0.01, (
                f"Token '{token}' has df/N={ratio:.3f} > 0.60, "
                f"but IDF={idf_value} (expected < 0.01)"
            )
        else:
            # Standard IDF formula: log(N / df)
            expected_idf = math.log(N / df)
            assert math.isclose(idf_value, expected_idf, rel_tol=1e-9), (
                f"Token '{token}' has df/N={ratio:.3f} <= 0.60, "
                f"IDF={idf_value} but expected log({N}/{df})={expected_idf}"
            )


# ---------------------------------------------------------------------------
# Feature: lexical-semantic-upgrade, Property 2: TF-IDF Score Bounds Invariant
# **Validates: Requirements 2.1**
#
# Property 2: For any prompt string and for any knowledge base corpus, the
# TF-IDF score returned by the Lexical Engine SHALL be a float in the range
# [0.0, 1.0] inclusive.
# ---------------------------------------------------------------------------


# Strategy: generate random document sets for Property 2
@st.composite
def random_corpus_strategy(draw):
    """Generate a random corpus of documents with arbitrary text content."""
    num_docs = draw(st.integers(min_value=1, max_value=50))
    documents = []
    for _ in range(num_docs):
        content = draw(st.text(min_size=1, max_size=200))
        documents.append({
            "path": "test/random.md",
            "filename": "random.md",
            "category": "test",
            "content": content,
        })
    return documents


@given(
    prompt=st.text(min_size=0, max_size=300),
    documents=random_corpus_strategy(),
)
@settings(max_examples=200, deadline=None)
def test_tfidf_score_bounds(prompt, documents):
    """
    Property 2: TF-IDF Score Bounds Invariant.

    For any prompt string and for any knowledge base corpus, the TF-IDF
    score returned by the Lexical Engine SHALL be a float in [0.0, 1.0].
    """
    config = LexicalConfig()
    engine = LexicalEngine(documents, config=config)
    result = engine.score(prompt)

    assert isinstance(result.tfidf_score, float), (
        f"tfidf_score should be a float, got {type(result.tfidf_score)}"
    )
    assert 0.0 <= result.tfidf_score <= 1.0, (
        f"tfidf_score={result.tfidf_score} is out of bounds [0.0, 1.0] "
        f"for prompt={prompt!r} with {len(documents)} documents"
    )


# ---------------------------------------------------------------------------
# Feature: lexical-semantic-upgrade, Property 3: Lexical Verdict Threshold Consistency
# **Validates: Requirements 2.2, 2.3, 2.4**
#
# Property 3: For any prompt and corpus, the verdict returned by the Lexical
# Engine SHALL be exactly:
# - PUBLIC when tfidf_score < public_threshold
# - AMBIGUOUS when public_threshold <= tfidf_score < enterprise_threshold
# - ENTERPRISE_LIKELY when tfidf_score >= enterprise_threshold
#
# These three cases are mutually exclusive and exhaustive for all scores in
# [0.0, 1.0].
# ---------------------------------------------------------------------------


# Strategy: generate valid threshold pairs (public < enterprise, both in (0.0, 1.0))
@st.composite
def threshold_pair_strategy(draw):
    """Generate a valid (public_threshold, enterprise_threshold) pair."""
    # Draw two distinct values in (0.01, 0.99) and order them
    t1 = draw(st.floats(min_value=0.01, max_value=0.99, allow_nan=False, allow_infinity=False))
    t2 = draw(st.floats(min_value=0.01, max_value=0.99, allow_nan=False, allow_infinity=False))
    assume(abs(t1 - t2) > 0.01)  # Ensure they are sufficiently distinct
    public_threshold = min(t1, t2)
    enterprise_threshold = max(t1, t2)
    return public_threshold, enterprise_threshold


@given(
    prompt=st.text(min_size=0, max_size=300),
    documents=random_corpus_strategy(),
    thresholds=threshold_pair_strategy(),
)
@settings(max_examples=200, deadline=None)
def test_verdict_threshold_consistency(prompt, documents, thresholds):
    """
    Property 3: Lexical Verdict Threshold Consistency.

    For any prompt and corpus, the verdict returned by the Lexical Engine is
    consistent with the tfidf_score and the configured thresholds:
    - PUBLIC when tfidf_score < public_threshold
    - AMBIGUOUS when public_threshold <= tfidf_score < enterprise_threshold
    - ENTERPRISE_LIKELY when tfidf_score >= enterprise_threshold

    The three verdicts are mutually exclusive and exhaustive.
    """
    public_threshold, enterprise_threshold = thresholds

    config = LexicalConfig()
    config.public_threshold = public_threshold
    config.enterprise_threshold = enterprise_threshold

    engine = LexicalEngine(documents, config=config)
    result = engine.score(prompt)

    score = result.tfidf_score
    verdict = result.verdict

    # Verify verdict matches threshold boundaries exactly
    if score < public_threshold:
        expected_verdict = "PUBLIC"
    elif score >= enterprise_threshold:
        expected_verdict = "ENTERPRISE_LIKELY"
    else:
        expected_verdict = "AMBIGUOUS"

    assert verdict == expected_verdict, (
        f"Verdict mismatch: score={score}, "
        f"public_threshold={public_threshold}, enterprise_threshold={enterprise_threshold}, "
        f"got verdict={verdict!r}, expected={expected_verdict!r}"
    )

    # Verify mutual exclusivity: verdict must be exactly one of the three valid values
    valid_verdicts = {"PUBLIC", "AMBIGUOUS", "ENTERPRISE_LIKELY"}
    assert verdict in valid_verdicts, (
        f"Verdict {verdict!r} is not one of {valid_verdicts}"
    )
