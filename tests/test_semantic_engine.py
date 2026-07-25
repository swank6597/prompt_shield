# Feature: lexical-semantic-upgrade, Property 5: Semantic Search Score Bounds and Ordering
# **Validates: Requirements 4.1, 4.2**
#
# Property 5: For any prompt and for any FAISS index of embedded chunks, the
# semantic similarity score returned by the Semantic Engine SHALL be in
# [0.0, 1.0], and the returned top-k chunks SHALL be sorted by descending
# similarity score.

import os
import sys
import tempfile
from unittest.mock import patch, MagicMock

import numpy as np

# Path setup so we can import from backend/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend", "ai"))

import faiss
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from ai.semantic_engine import SemanticEngine, SemanticConfig, SemanticResult


# ---------------------------------------------------------------------------
# Test fixtures and helpers
# ---------------------------------------------------------------------------

def _random_normalized_vectors(n: int, dim: int, rng: np.random.Generator) -> np.ndarray:
    """Generate n random unit-normalized vectors of given dimension."""
    vecs = rng.standard_normal((n, dim)).astype(np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-10)
    return vecs / norms


def _build_test_engine(num_chunks: int, dim: int, seed: int) -> SemanticEngine:
    """
    Build a SemanticEngine with a real FAISS index containing random
    normalized embeddings and a mock embedding model.

    The mock model returns a random normalized embedding for any input prompt.
    This lets us test the search/score logic end-to-end without needing
    sentence-transformers installed.
    """
    rng = np.random.default_rng(seed)

    # Create random chunk embeddings and build FAISS index
    embeddings = _random_normalized_vectors(num_chunks, dim, rng)
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)

    # Create chunk metadata
    chunks = []
    for i in range(num_chunks):
        chunks.append({
            "text": f"Test chunk {i} content.",
            "source_filename": f"doc_{i % 3}.md",
            "category": "test",
            "heading": f"Section {i}",
        })

    # Build a SemanticEngine with internals manually set (bypassing __init__)
    with tempfile.TemporaryDirectory() as tmp_dir:
        cfg = SemanticConfig(
            model_name="mock-model",
            chunk_size=500,
            index_dir=tmp_dir,
        )

    # Create the engine without triggering real initialization
    engine = object.__new__(SemanticEngine)
    engine.config = cfg
    engine.documents = []
    engine.available = True
    engine._index = index
    engine._chunks = chunks

    # Mock model that returns a random normalized vector for any input
    mock_model = MagicMock()

    def mock_encode(texts, **kwargs):
        """Return random normalized embeddings for any input texts."""
        n = len(texts)
        vecs = rng.standard_normal((n, dim)).astype(np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms = np.maximum(norms, 1e-10)
        return vecs / norms

    mock_model.encode = mock_encode
    engine._model = mock_model

    return engine


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Strategy for generating prompt strings
prompt_strategy = st.text(min_size=0, max_size=200)

# Strategy for top_k values
top_k_strategy = st.integers(min_value=1, max_value=20)

# Strategy for the number of chunks in the test index
num_chunks_strategy = st.integers(min_value=1, max_value=50)

# Strategy for embedding dimension
dim_strategy = st.sampled_from([32, 64, 128, 384])

# Strategy for seed (for reproducibility within a test run)
seed_strategy = st.integers(min_value=0, max_value=2**31 - 1)


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------

@given(
    prompt=prompt_strategy,
    top_k=top_k_strategy,
    num_chunks=num_chunks_strategy,
    dim=dim_strategy,
    seed=seed_strategy,
)
@settings(max_examples=200, deadline=None)
def test_semantic_score_bounds_and_ordering(prompt, top_k, num_chunks, dim, seed):
    """
    Property 5: Semantic Search Score Bounds and Ordering.

    For any prompt and for any FAISS index of embedded chunks:
    1. The semantic_score SHALL be in [0.0, 1.0]
    2. Each individual chunk score SHALL be in [0.0, 1.0]
    3. The returned top_chunks SHALL be sorted by descending similarity score
    """
    engine = _build_test_engine(num_chunks, dim, seed)
    result = engine.search(prompt, top_k=top_k)

    # --- Assertion 1: semantic_score is in [0.0, 1.0] ---
    assert isinstance(result.semantic_score, float), (
        f"semantic_score should be float, got {type(result.semantic_score)}"
    )
    assert 0.0 <= result.semantic_score <= 1.0, (
        f"semantic_score={result.semantic_score} is out of bounds [0.0, 1.0] "
        f"for prompt={prompt!r}, top_k={top_k}, num_chunks={num_chunks}"
    )

    # --- Assertion 2: Each chunk score is in [0.0, 1.0] ---
    for i, chunk in enumerate(result.top_chunks):
        score = chunk["score"]
        assert 0.0 <= score <= 1.0, (
            f"Chunk {i} score={score} is out of bounds [0.0, 1.0] "
            f"for prompt={prompt!r}"
        )

    # --- Assertion 3: Chunks are sorted by descending score ---
    if len(result.top_chunks) > 1:
        scores = [c["score"] for c in result.top_chunks]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], (
                f"Chunks not sorted by descending score: "
                f"scores[{i}]={scores[i]} < scores[{i+1}]={scores[i+1]}. "
                f"Full scores: {scores}"
            )

    # --- Additional invariant: semantic_score == max of chunk scores ---
    if result.top_chunks:
        max_chunk_score = max(c["score"] for c in result.top_chunks)
        assert result.semantic_score == max_chunk_score, (
            f"semantic_score={result.semantic_score} should equal "
            f"max chunk score={max_chunk_score}"
        )

    # --- Invariant: number of returned chunks <= min(top_k, num_chunks) ---
    expected_max_chunks = min(top_k, num_chunks)
    assert len(result.top_chunks) <= expected_max_chunks, (
        f"Got {len(result.top_chunks)} chunks but expected at most "
        f"{expected_max_chunks} (top_k={top_k}, num_chunks={num_chunks})"
    )


# ---------------------------------------------------------------------------
# Feature: lexical-semantic-upgrade, Property 4: Document Chunking Size Bounds
# **Validates: Requirements 3.4**
#
# Property 4: For any Markdown document, every chunk produced by the Semantic
# Engine's chunking function SHALL have a length of at most 2 * chunk_size
# characters, and the concatenation of all chunks (ignoring heading splits)
# SHALL preserve all non-whitespace content from the original document.
# ---------------------------------------------------------------------------

import re as _re

# Strategy: generate a Markdown heading line
_heading_st = st.from_regex(r"## [A-Za-z][A-Za-z0-9 ]{1,40}", fullmatch=True)

# Strategy: generate a paragraph of text (no double newlines inside)
_paragraph_st = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S", "Zs"),
        blacklist_characters="\x00",
    ),
    min_size=1,
    max_size=300,
).map(lambda s: s.replace("\n\n", "\n").strip()).filter(lambda s: len(s) > 0)


@st.composite
def markdown_document_strategy(draw):
    """
    Generate a random Markdown document with headings and paragraphs.

    Structure: optional paragraphs before first heading, then 1-5 sections
    each starting with a ## heading followed by 1-4 paragraphs.
    """
    parts = []

    # Optional leading content before any heading
    if draw(st.booleans()):
        intro_paras = draw(st.lists(_paragraph_st, min_size=1, max_size=3))
        parts.append("\n\n".join(intro_paras))

    # Generate 1-5 sections with headings
    num_sections = draw(st.integers(min_value=1, max_value=5))
    for _ in range(num_sections):
        heading = draw(_heading_st)
        paras = draw(st.lists(_paragraph_st, min_size=1, max_size=4))
        section = heading + "\n\n" + "\n\n".join(paras)
        parts.append(section)

    return "\n\n".join(parts)


def _non_whitespace(text: str) -> str:
    """Return all non-whitespace characters from text in order."""
    return _re.sub(r"\s+", "", text)


def _strip_headings(text: str) -> str:
    """Remove Markdown ## heading lines from text (these become metadata, not chunk content)."""
    return _re.sub(r"(?m)^##\s+.+$", "", text)


@given(content=markdown_document_strategy())
@settings(max_examples=200, deadline=None)
def test_document_chunking_size_bounds(content):
    """
    Property 4: Document Chunking Size Bounds.

    For any Markdown document:
    1. Every chunk produced by _chunk_documents has length <= 2 * chunk_size
    2. The concatenation of all chunk texts (ignoring heading splits)
       preserves all non-whitespace content from the original document.
       "Ignoring heading splits" means ## heading lines are used as structural
       delimiters and stored as metadata, so their text is excluded from chunks.
    """
    # Use a smaller chunk_size to exercise splitting more aggressively
    chunk_size = 200

    # Create a SemanticConfig without loading any model (we only test chunking)
    config = SemanticConfig()
    config.chunk_size = chunk_size

    # Build a document dict matching the expected input format
    doc = {
        "path": "test/doc.md",
        "filename": "doc.md",
        "category": "test",
        "content": content,
    }

    # Directly call _chunk_documents without full engine initialization
    # We create a minimal engine instance just to access the method
    engine = SemanticEngine.__new__(SemanticEngine)
    engine.config = config

    chunks = engine._chunk_documents([doc])

    # Property 4a: Every chunk has length <= 2 * chunk_size
    for i, chunk in enumerate(chunks):
        chunk_text = chunk["text"]
        assert len(chunk_text) <= 2 * chunk_size, (
            f"Chunk {i} exceeds size bound: len={len(chunk_text)}, "
            f"max allowed={2 * chunk_size}. "
            f"Chunk text (first 100 chars): {chunk_text[:100]!r}"
        )

    # Property 4b: Concatenation of all chunks preserves all non-whitespace content
    # (ignoring heading splits — headings are stored as metadata, not in chunk text)
    all_chunk_text = "".join(chunk["text"] for chunk in chunks)
    content_without_headings = _strip_headings(content)
    original_non_ws = _non_whitespace(content_without_headings)
    chunked_non_ws = _non_whitespace(all_chunk_text)

    assert chunked_non_ws == original_non_ws, (
        f"Non-whitespace content mismatch (after removing heading lines).\n"
        f"Original length: {len(original_non_ws)}\n"
        f"Chunked length: {len(chunked_non_ws)}\n"
        f"Original (first 200): {original_non_ws[:200]!r}\n"
        f"Chunked (first 200): {chunked_non_ws[:200]!r}"
    )
