# lexical_engine.py
# TF-IDF scoring engine with inverted index for fast deterministic
# prompt scoring against the enterprise knowledge base. Replaces the
# naive token-overlap approach in keyword_search.py with proper term
# weighting and high-frequency dampening (no manual stopword list).

import math
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field

_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from utils.logger import get_logger  # noqa: E402
import config  # noqa: E402

log = get_logger("lexical_engine")


@dataclass
class LexicalConfig:
    """Configuration for the Lexical Engine thresholds."""
    public_threshold: float = config.TFIDF_PUBLIC_THRESHOLD
    enterprise_threshold: float = config.TFIDF_ENTERPRISE_THRESHOLD
    high_df_cutoff: float = 0.60  # tokens in >60% docs get near-zero IDF


@dataclass
class LexicalResult:
    """Result of scoring a prompt against the inverted index."""
    tfidf_score: float = 0.0        # Normalized 0.0-1.0
    verdict: str = "PUBLIC"          # "PUBLIC" | "AMBIGUOUS" | "ENTERPRISE_LIKELY"
    top_docs: list = field(default_factory=list)    # Top matching documents with scores
    matched_terms: list = field(default_factory=list)  # Terms that contributed to the score


class LexicalEngine:
    """TF-IDF scoring engine with inverted index."""

    def __init__(self, documents: list[dict], config: LexicalConfig | None = None):
        """
        Build inverted index from knowledge base documents.

        Args:
            documents: List of dicts from context_loader
                       (keys: path, filename, category, content)
            config: Configuration object with thresholds. Uses defaults
                    from config.py if not provided.
        """
        self.config = config or LexicalConfig()
        self.documents = documents
        self.num_docs = len(documents)

        # Inverted index: token -> {"df": int, "postings": [(doc_id, tf), ...]}
        self.inverted_index: dict[str, dict] = {}
        # IDF cache: token -> idf value
        self.idf_cache: dict[str, float] = {}

        if self.num_docs == 0:
            log.warning("LexicalEngine initialized with empty document set. "
                        "All prompts will score 0.0 (PUBLIC).")
        else:
            self._build_index(documents)

    def _tokenize(self, text: str) -> list[str]:
        """
        Tokenize text into lowercase alphanumeric tokens.

        Uses regex [a-zA-Z][a-zA-Z0-9_-]+ to extract tokens, converts
        to lowercase, and filters out tokens with length <= 2.
        No stopword list — high-frequency suppression is handled by
        IDF dampening.
        """
        words = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]+", text.lower())
        return [w for w in words if len(w) > 2]

    def _build_index(self, documents: list[dict]) -> None:
        """
        Build inverted index: token -> {df, postings[(doc_id, tf)]}.
        Also precomputes IDF values with high-frequency dampening.
        """
        for doc_id, doc in enumerate(documents):
            tokens = self._tokenize(doc.get("content", ""))
            token_counts = Counter(tokens)

            for token, tf in token_counts.items():
                if token not in self.inverted_index:
                    self.inverted_index[token] = {"df": 0, "postings": []}
                self.inverted_index[token]["postings"].append((doc_id, tf))
                self.inverted_index[token]["df"] += 1

        # Precompute IDF values with high-frequency dampening
        for token, entry in self.inverted_index.items():
            df = max(entry["df"], 1)  # Guard against division by zero
            ratio = df / self.num_docs

            if ratio > self.config.high_df_cutoff:
                # High-frequency dampening: near-zero IDF for generic terms
                self.idf_cache[token] = 0.0
            else:
                self.idf_cache[token] = math.log(self.num_docs / df)

        log.info(
            "Built inverted index: %d unique tokens from %d documents",
            len(self.inverted_index), self.num_docs
        )

    def score(self, prompt: str) -> LexicalResult:
        """
        Score a prompt against the inverted index using TF-IDF.

        Args:
            prompt: Raw user prompt text

        Returns:
            LexicalResult with tfidf_score, verdict, top_docs, matched_terms
        """
        # Handle empty knowledge base
        if self.num_docs == 0:
            return LexicalResult(
                tfidf_score=0.0,
                verdict="PUBLIC",
                top_docs=[],
                matched_terms=[],
            )

        # Tokenize prompt
        prompt_tokens = self._tokenize(prompt)

        # Handle empty token list
        if not prompt_tokens:
            return LexicalResult(
                tfidf_score=0.0,
                verdict="PUBLIC",
                top_docs=[],
                matched_terms=[],
            )

        # Count term frequencies in the prompt
        prompt_tf = Counter(prompt_tokens)

        # Compute raw TF-IDF score and track matched terms
        raw_score = 0.0
        matched_terms = []

        for token, tf in prompt_tf.items():
            if token in self.idf_cache:
                idf = self.idf_cache[token]
                if idf > 0.0:
                    raw_score += tf * idf
                    matched_terms.append(token)

        # Compute max possible score for normalization:
        # Each unique prompt token contributes at most tf * max_idf
        # where max_idf = log(N / 1) = log(N) (rarest possible term)
        max_idf = math.log(self.num_docs) if self.num_docs > 1 else 1.0
        max_score = sum(tf * max_idf for tf in prompt_tf.values())

        # Normalize to 0.0-1.0
        if max_score > 0.0:
            normalized_score = min(raw_score / max_score, 1.0)
        else:
            normalized_score = 0.0

        # Determine verdict based on thresholds
        if normalized_score >= self.config.enterprise_threshold:
            verdict = "ENTERPRISE_LIKELY"
        elif normalized_score >= self.config.public_threshold:
            verdict = "AMBIGUOUS"
        else:
            verdict = "PUBLIC"

        # Compute per-document scores for top_docs
        doc_scores: dict[int, float] = {}
        for token, tf in prompt_tf.items():
            if token in self.inverted_index and token in self.idf_cache:
                idf = self.idf_cache[token]
                if idf > 0.0:
                    for doc_id, _doc_tf in self.inverted_index[token]["postings"]:
                        if doc_id not in doc_scores:
                            doc_scores[doc_id] = 0.0
                        doc_scores[doc_id] += tf * idf

        # Sort documents by score and take top matches
        sorted_docs = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)
        top_docs = []
        for doc_id, doc_score in sorted_docs[:5]:
            doc = self.documents[doc_id]
            top_docs.append({
                "filename": doc["filename"],
                "category": doc["category"],
                "score": round(doc_score, 4),
            })

        return LexicalResult(
            tfidf_score=round(normalized_score, 6),
            verdict=verdict,
            top_docs=top_docs,
            matched_terms=sorted(matched_terms),
        )


if __name__ == "__main__":
    # Quick manual test
    from context_loader import load_knowledge_base

    docs = load_knowledge_base()
    engine = LexicalEngine(docs)

    test_prompts = [
        "Explain OAuth2.",
        "Explain our OAuth2 implementation.",
        "Why does the Mercury payment flow retry before failing over?",
        "What's the capital of France?",
        "How does the Orion identity service handle token refresh?",
        "",
    ]

    for p in test_prompts:
        result = engine.score(p)
        print(f"\nPrompt: {p!r}")
        print(f"  Score: {result.tfidf_score:.4f}  Verdict: {result.verdict}")
        print(f"  Matched: {result.matched_terms}")
        if result.top_docs:
            print(f"  Top doc: {result.top_docs[0]}")
