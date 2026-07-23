# context_loader.py
# Loads and caches the enterprise knowledge base (Markdown files under
# /knowledge) into memory for use by keyword_search.py. Version 1: no
# knowledge_index.json dependency yet - just walks the folder directly.
# Once Ranjith's knowledge_index.json is populated, this can be swapped
# to read the index instead of walking the filesystem, without changing
# keyword_search.py's interface.

import os
import sys

# knowledge/ lives at the project root, two levels up from backend/ai/
KNOWLEDGE_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "knowledge")
)

_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from utils.logger import get_logger  # noqa: E402

log = get_logger("context_loader")

_cache = None  # simple in-memory cache; reset with force_reload=True


def load_knowledge_base(force_reload: bool = False) -> list[dict]:
    """
    Walks KNOWLEDGE_DIR and loads every .md file into memory.

    Returns a list of dicts:
        {
            "path": "<absolute file path>",
            "filename": "oauth2-implementation.md",
            "category": "security",   # top-level knowledge/ subfolder
            "content": "<full file text>"
        }
    """
    global _cache
    if _cache is not None and not force_reload:
        log.debug("Using cached knowledge base (%d docs)", len(_cache))
        return _cache

    docs = []
    for root, _dirs, files in os.walk(KNOWLEDGE_DIR):
        for fname in files:
            if not fname.endswith(".md"):
                continue
            path = os.path.join(root, fname)
            # category = the immediate subfolder under knowledge/, e.g. "security"
            rel = os.path.relpath(root, KNOWLEDGE_DIR)
            category = rel.split(os.sep)[0] if rel != "." else "uncategorized"

            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            docs.append({
                "path": path,
                "filename": fname,
                "category": category,
                "content": content,
            })

    log.info("Loaded %d knowledge document(s) from %s", len(docs), KNOWLEDGE_DIR)
    _cache = docs
    return docs


if __name__ == "__main__":
    # Quick manual check: python context_loader.py
    loaded = load_knowledge_base()
    print(f"Loaded {len(loaded)} knowledge document(s) from {KNOWLEDGE_DIR}:")
    for d in loaded:
        print(f"  [{d['category']}] {d['filename']} ({len(d['content'])} chars)")
