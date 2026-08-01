# lexical_engine.py
# TF-IDF scoring engine with inverted index for fast deterministic
# prompt scoring against the enterprise knowledge base. Replaces the
# naive token-overlap approach in keyword_search.py with proper term
# weighting, high-frequency dampening, and an explicit stoplist (see
# STOPWORDS below for why dampening alone was not sufficient).

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


# =============================================================================
# Stoplist
# =============================================================================
# Why an explicit list at all, when this engine already dampens high-DF terms:
# the dampening threshold (high_df_cutoff, 0.60) only fires for tokens present
# in more than ~29 of the 48 knowledge documents. The corpus is declarative
# documentation - specs and runbooks - so question words and doc/meta verbs
# barely occur in it and therefore land at or near *maximum* IDF, where the
# scorer cannot distinguish them from genuinely rare internal jargon.
#
# Measured on the real 48-document corpus (max attainable IDF = 3.8712):
#
#     what       df=1/48   idf=3.8712   <- ties the rarest real enterprise term
#     how        df=1/48   idf=3.8712
#     doc        df=1/48   idf=3.8712
#     other      df=1/48   idf=3.8712
#     does       df=2/48   idf=3.1781
#     involved   df=2/48   idf=3.1781
#     company    df=2/48   idf=3.1781
#     can                  idf=2.4849
#     reviewing  df=5/48   idf=2.2618
#     level      df=10/48  idf=1.5686
#     high       df=15/48  idf=1.1632
#     mercury              idf=0.5390   <- an ACTUAL product name, ~7x lower
#
# So "What is GDPR?" outscored a prompt naming a dozen real internal systems.
# The fix is lexical, not a threshold change: these tokens must not enter the
# index or the query at all.
#
# The list is a module-level constant, and deliberately a *copy* of
# keyword_search.STOPWORDS rather than an import of it. keyword_search.py is
# retained only to serve the USE_LEGACY_SEARCH rollback path and is expected to
# be deleted once that rollback is no longer needed; importing from it would
# couple the live scoring path to a module on its way out, and would pull
# keyword_search's module-level `from context_loader import load_knowledge_base`
# into lexical_engine's import graph, which the tests import directly without
# the ai/ directory necessarily on sys.path. The two lists are allowed to
# diverge: this one is tuned for IDF weighting, that one for raw token overlap.
#
# Tokens of length <= 2 are dropped by _tokenize()'s length filter regardless;
# the short entries below are kept so the list reads as a complete stoplist.
STOPWORDS = frozenset({
    # --- copied verbatim from keyword_search.STOPWORDS (origin, see above) ---
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "our", "my", "your", "their", "his", "her", "its", "to", "of", "in",
    "on", "for", "and", "or", "this", "that", "these", "those", "explain",
    "what", "how", "why", "does", "do", "did", "i", "we", "you", "it",
    "with", "as", "at", "by", "from", "about",

    # --- interrogatives and hedges (rare in declarative docs -> max IDF) ---
    "which", "when", "where", "who", "whom", "whose",
    "typically", "generally", "general", "roughly", "reasonable",

    # --- doc/meta verbs: describe the request, not its subject ---
    "detailed", "detail", "exactly", "summarize", "describe", "draft",
    "review", "reviewing",

    # --- generic relational / positional filler ---
    "involved", "before", "after", "other", "others", "another",
    "high", "level", "kind", "sort", "type",

    # --- modals and politeness ---
    "can", "could", "would", "should", "need", "needs", "want",
    "help", "please", "tell", "show", "give",

    # --- generic verbs and prepositions ---
    "make", "made", "using", "used", "use", "into", "onto", "over",
    "under", "than", "then", "there", "here", "also",

    # --- quantifiers and negation ---
    "such", "some", "any", "each", "both", "more", "most", "less",
    "very", "much", "many", "not", "but",

    # --- document/abstraction nouns ---
    "doc", "docs", "document", "documents", "terms", "term",
    "thing", "things", "way", "ways", "work", "works", "working",

    # --- conversational filler ---
    "get", "got", "know", "like", "just", "really",
    "actual", "actually", "full", "new", "old", "same", "different",

    # --- generic business vocabulary present in almost any phrasing ---
    "between", "versus", "vers", "matter", "matters",
    "processes", "process", "digital", "company", "companies",
    "team", "teams", "target", "response", "time", "times",
})


@dataclass
class LexicalConfig:
    """Configuration for the Lexical Engine thresholds."""
    public_threshold: float = config.TFIDF_PUBLIC_THRESHOLD
    enterprise_threshold: float = config.TFIDF_ENTERPRISE_THRESHOLD
    high_df_cutoff: float = 0.60  # tokens in >60% docs get near-zero IDF
    # Saturation constant for magnitude normalization: score = raw / (raw + K).
    # K is the raw score at which the normalized score reaches 0.5.
    saturation_k: float = config.LEXICAL_SATURATION_K


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

        Uses regex [a-zA-Z][a-zA-Z0-9_-]+ to extract tokens, converts to
        lowercase, drops tokens with length <= 2, and drops STOPWORDS.

        IDF dampening (high_df_cutoff) suppresses terms that are *common* in
        the corpus; the stoplist suppresses terms that are common in English
        but rare in this corpus, which dampening by construction cannot see.
        See the STOPWORDS comment for the measured IDF values.

        This is the single tokenization entry point for both _build_index()
        and score(), so the stoplist is applied to the indexed corpus and to
        the query identically and the IDF table stays consistent with it.
        """
        words = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]+", text.lower())
        return [w for w in words if len(w) > 2 and w not in STOPWORDS]

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

        # Normalize to 0.0-1.0 by saturating magnitude, NOT by density.
        #
        # The previous formula divided raw_score by sum(tf * max_idf) over every
        # prompt token. That denominator grows with total prompt length while
        # only corpus-matching tokens raise the numerator, so the result was a
        # density measure: rephrasing the same question more verbosely lowered
        # its score, and a two-token generic question could reach 1.0 while a
        # prompt naming a dozen real internal systems scored ~0.2.
        #
        # raw / (raw + K) instead measures accumulated evidence. It is strictly
        # increasing in raw_score and bounded in [0.0, 1.0) for raw >= 0, K > 0,
        # so more matched enterprise weight always means a higher score.
        denominator = raw_score + self.config.saturation_k
        if denominator > 0.0:
            normalized_score = raw_score / denominator
        else:
            # Only reachable if saturation_k is misconfigured to <= 0.
            normalized_score = 0.0

        # Defensive clamp: guarantees the documented [0.0, 1.0] contract even
        # if saturation_k is configured to a nonsensical (negative) value.
        normalized_score = max(0.0, min(normalized_score, 1.0))

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
