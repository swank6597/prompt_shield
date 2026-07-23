# keyword_search.py
# Version 1 knowledge retrieval - extracts keywords from the (masked)
# prompt and scores loaded knowledge documents by simple token overlap
# to select the most relevant snippet(s). No embeddings/vector DB -
# that's explicitly future work per the project doc.

import re
from collections import Counter

from context_loader import load_knowledge_base

# Common words that carry no topical signal - excluded so they don't
# inflate every document's score equally.
STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "our", "my", "your", "their", "his", "her", "its", "to", "of", "in",
    "on", "for", "and", "or", "this", "that", "these", "those", "explain",
    "what", "how", "why", "does", "do", "did", "i", "we", "you", "it",
    "with", "as", "at", "by", "from", "about",
}


def _tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]+", text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 2]


def search(prompt: str, top_k: int = 2, min_score: int = 1) -> list[dict]:
    """
    Scores every loaded knowledge document against the prompt's keywords
    and returns the top_k highest-scoring matches.

    Returns a list of dicts (subset of context_loader's doc dict, plus
    "score"):
        {"path": ..., "filename": ..., "category": ..., "content": ..., "score": int}

    Returns an empty list if nothing scores >= min_score - callers
    (prompt_builder.py) should handle "no relevant enterprise knowledge
    found" as a valid, common case, not an error.
    """
    documents = load_knowledge_base()
    prompt_tokens = set(_tokenize(prompt))

    if not prompt_tokens:
        return []

    scored = []
    for doc in documents:
        doc_counter = Counter(_tokenize(doc["content"]))
        score = sum(doc_counter[t] for t in prompt_tokens if t in doc_counter)
        if score >= min_score:
            scored.append({**doc, "score": score})

    scored.sort(key=lambda d: d["score"], reverse=True)
    return scored[:top_k]


if __name__ == "__main__":
    # Quick manual check: python keyword_search.py
    test_prompts = [
        "Explain OAuth2.",
        "Explain our OAuth2 implementation.",
        "Why does the Mercury payment flow retry before failing over?",
        "What's the capital of France?",
    ]
    for p in test_prompts:
        results = search(p)
        print(f"\nPrompt: {p!r}")
        if not results:
            print("  -> no relevant enterprise knowledge found")
        for r in results:
            print(f"  -> [{r['category']}] {r['filename']} (score={r['score']})")
