"""
Tests for backend/ai/prompt_builder.py

Validates:
- Semantic chunks formatting
- Fallback to full documents when no chunks provided
- Output structure preservation (system + user keys with non-empty strings)
"""

import sys
import os

# Add backend to path so prompt_builder can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend", "ai"))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from prompt_builder import build_prompt, _format_semantic_chunks, NO_KNOWLEDGE_MESSAGE


class TestFormatSemanticChunks:
    """Tests for _format_semantic_chunks helper."""

    def test_empty_list_returns_no_knowledge_message(self):
        result = _format_semantic_chunks([])
        assert result == NO_KNOWLEDGE_MESSAGE

    def test_none_returns_no_knowledge_message(self):
        # The function guards against falsy input
        result = _format_semantic_chunks(None)
        assert result == NO_KNOWLEDGE_MESSAGE

    def test_single_chunk_formatted(self):
        chunks = [{"text": "OAuth2 flow details", "source_doc": "Identity-api.md", "score": 0.85}]
        result = _format_semantic_chunks(chunks)
        assert "Semantic Match: Identity-api.md" in result
        assert "relevance: 0.85" in result
        assert "OAuth2 flow details" in result

    def test_multiple_chunks_formatted(self):
        chunks = [
            {"text": "First chunk text", "source_doc": "doc1.md", "score": 0.9},
            {"text": "Second chunk text", "source_doc": "doc2.md", "score": 0.7},
        ]
        result = _format_semantic_chunks(chunks)
        assert "First chunk text" in result
        assert "Second chunk text" in result
        assert "doc1.md" in result
        assert "doc2.md" in result

    def test_missing_keys_use_defaults(self):
        chunks = [{"text": "some text"}]
        result = _format_semantic_chunks(chunks)
        assert "unknown" in result
        assert "0.00" in result
        assert "some text" in result


class TestBuildPrompt:
    """Tests for the updated build_prompt function."""

    def test_output_has_system_and_user_keys(self):
        result = build_prompt("test prompt")
        assert "system" in result
        assert "user" in result
        assert isinstance(result["system"], str)
        assert isinstance(result["user"], str)
        assert len(result["system"]) > 0
        assert len(result["user"]) > 0

    def test_no_docs_no_chunks_uses_no_knowledge_message(self):
        result = build_prompt("test prompt")
        assert NO_KNOWLEDGE_MESSAGE in result["user"]

    def test_retrieved_docs_only_uses_full_format(self):
        docs = [{"filename": "api.md", "category": "apis", "content": "API documentation content"}]
        result = build_prompt("test prompt", retrieved_docs=docs)
        assert "api.md" in result["user"]
        assert "API documentation content" in result["user"]
        # Should NOT have semantic match formatting
        assert "Semantic Match" not in result["user"]

    def test_semantic_chunks_only_uses_chunk_format(self):
        chunks = [{"text": "OAuth2 implementation details", "source_doc": "Identity-api.md", "score": 0.92}]
        result = build_prompt("test prompt", semantic_chunks=chunks)
        assert "Semantic Match: Identity-api.md" in result["user"]
        assert "OAuth2 implementation details" in result["user"]
        assert "relevance: 0.92" in result["user"]

    def test_semantic_chunks_with_docs_includes_both(self):
        docs = [{"filename": "full-doc.md", "category": "apis", "content": "Full document content"}]
        chunks = [{"text": "Targeted chunk", "source_doc": "full-doc.md", "score": 0.88}]
        result = build_prompt("test prompt", retrieved_docs=docs, semantic_chunks=chunks)
        # Should have semantic chunks
        assert "Semantic Match: full-doc.md" in result["user"]
        assert "Targeted chunk" in result["user"]
        # Should also have full docs as supplementary
        assert "Full Source Documents" in result["user"]
        assert "Full document content" in result["user"]

    def test_empty_semantic_chunks_falls_back_to_docs(self):
        docs = [{"filename": "api.md", "category": "apis", "content": "Full doc"}]
        result = build_prompt("test prompt", retrieved_docs=docs, semantic_chunks=[])
        # Empty list is falsy, should fall back to docs
        assert "api.md" in result["user"]
        assert "Full doc" in result["user"]
        assert "Semantic Match" not in result["user"]

    def test_masked_text_included_in_output(self):
        result = build_prompt("my sensitive prompt here")
        assert "my sensitive prompt here" in result["user"]

    def test_system_prompt_contains_schema(self):
        result = build_prompt("test")
        # The system prompt should have schema instructions from schema.json
        assert "json" in result["system"].lower()

    def test_preserves_prompt_structure_placeholders_replaced(self):
        result = build_prompt("classify this")
        # Placeholders should be replaced, not present in output
        assert "{{RETRIEVED_KNOWLEDGE}}" not in result["user"]
        assert "{{MASKED_PROMPT}}" not in result["user"]
        assert "{{SCHEMA_INSTRUCTIONS}}" not in result["system"]


# ---------------------------------------------------------------------------
# Property-Based Tests (Hypothesis) - Property 9: Prompt Builder Context Inclusion
# Validates: Requirements 7.1, 7.2, 7.3
# ---------------------------------------------------------------------------

# Strategies for generating random test data
_text_alphabet = st.characters(whitelist_categories=('L', 'N', 'P', 'Z'))
_text_strategy = st.text(min_size=1, max_size=100, alphabet=_text_alphabet)
_score_strategy = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)

_chunk_strategy = st.fixed_dictionaries({
    "text": _text_strategy,
    "source_doc": _text_strategy,
    "score": _score_strategy,
})

_doc_strategy = st.fixed_dictionaries({
    "filename": _text_strategy,
    "category": _text_strategy,
    "content": _text_strategy,
})

_chunks_list_strategy = st.lists(_chunk_strategy, min_size=1, max_size=5)
_docs_list_strategy = st.lists(_doc_strategy, min_size=1, max_size=5)


class TestPropertyPromptBuilderContextInclusion:
    """
    Property 9: Prompt Builder Context Inclusion

    **Validates: Requirements 7.1, 7.2, 7.3**
    """

    @given(
        masked_text=_text_strategy,
        chunks=_chunks_list_strategy,
    )
    @settings(max_examples=50)
    def test_property_chunks_appear_in_output(self, masked_text, chunks):
        """
        When semantic_chunks is non-empty, each chunk's text must appear
        in the result["user"] string.

        **Validates: Requirements 7.1**
        """
        result = build_prompt(masked_text, semantic_chunks=chunks)
        for chunk in chunks:
            assert chunk["text"] in result["user"], (
                f"Chunk text '{chunk['text'][:50]}...' not found in user prompt"
            )

    @given(
        masked_text=_text_strategy,
        docs=_docs_list_strategy,
    )
    @settings(max_examples=50)
    def test_property_fallback_to_docs_when_no_chunks(self, masked_text, docs):
        """
        When semantic_chunks is empty/None AND retrieved_docs is provided,
        the document content must appear in result["user"].

        **Validates: Requirements 7.2**
        """
        # Test with None chunks
        result_none = build_prompt(masked_text, retrieved_docs=docs, semantic_chunks=None)
        for doc in docs:
            assert doc["content"] in result_none["user"], (
                f"Doc content '{doc['content'][:50]}...' not found in user prompt (chunks=None)"
            )

        # Test with empty list chunks
        result_empty = build_prompt(masked_text, retrieved_docs=docs, semantic_chunks=[])
        for doc in docs:
            assert doc["content"] in result_empty["user"], (
                f"Doc content '{doc['content'][:50]}...' not found in user prompt (chunks=[])"
            )

    @given(
        masked_text=_text_strategy,
        docs=st.one_of(st.none(), _docs_list_strategy),
        chunks=st.one_of(st.none(), st.just([]), _chunks_list_strategy),
    )
    @settings(max_examples=50)
    def test_property_output_always_has_system_and_user(self, masked_text, docs, chunks):
        """
        For any combination of masked_text, retrieved_docs, and semantic_chunks,
        the result always has both "system" and "user" keys with non-empty string values.

        **Validates: Requirements 7.3**
        """
        result = build_prompt(masked_text, retrieved_docs=docs, semantic_chunks=chunks)
        assert "system" in result, "Result missing 'system' key"
        assert "user" in result, "Result missing 'user' key"
        assert isinstance(result["system"], str), "result['system'] is not a string"
        assert isinstance(result["user"], str), "result['user'] is not a string"
        assert len(result["system"]) > 0, "result['system'] is empty"
        assert len(result["user"]) > 0, "result['user'] is empty"
