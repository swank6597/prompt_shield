# semantic_engine.py
# Sentence-transformer embeddings + FAISS vector search engine for
# semantic similarity scoring of prompts against the enterprise
# knowledge base. Complements the lexical (TF-IDF) engine with
# meaning-aware retrieval that catches paraphrases and synonyms.

import json
import os
import re
import sys
from dataclasses import dataclass, field

_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from utils.logger import get_logger  # noqa: E402
import config  # noqa: E402

log = get_logger("semantic_engine")


@dataclass
class SemanticConfig:
    """Configuration for the Semantic Engine."""
    model_name: str = config.EMBEDDING_MODEL
    chunk_size: int = config.SEMANTIC_CHUNK_SIZE
    index_dir: str = os.path.join(os.path.dirname(__file__), "index")


@dataclass
class SemanticResult:
    """Result of a semantic search against the FAISS index."""
    semantic_score: float = 0.0             # 0.0-1.0 (max similarity from top-k)
    top_chunks: list = field(default_factory=list)   # [{text, source_doc, score}, ...]
    source_docs: list = field(default_factory=list)  # Unique source document filenames


class SemanticEngine:
    """Sentence-transformer embeddings + FAISS vector search."""

    def __init__(self, documents: list[dict], config: SemanticConfig | None = None):
        """
        Load or build FAISS index from knowledge base documents.

        Args:
            documents: List of dicts from context_loader
                       (keys: path, filename, category, content)
            config: Configuration with model name, chunk size, index path.
                    Uses defaults from config.py if not provided.
        """
        self.config = config or SemanticConfig()
        self.documents = documents
        self.available = False

        # These will be populated by _build_index or _load_persisted_index
        self._model = None
        self._index = None
        self._chunks: list[dict] = []

        # Attempt to load dependencies and initialize
        try:
            self._init_engine()
        except Exception as exc:
            log.error(
                "SemanticEngine initialization failed: %s. "
                "Engine marked unavailable; semantic scoring will be skipped.",
                exc,
            )
            self.available = False

    def _init_engine(self) -> None:
        """Load model and build/load FAISS index. Sets self.available on success."""
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            log.error(
                "sentence-transformers not installed. "
                "Install with: pip install sentence-transformers"
            )
            return

        try:
            import faiss  # noqa: F401
        except ImportError:
            log.error(
                "faiss-cpu not installed. "
                "Install with: pip install faiss-cpu"
            )
            return

        # Load the embedding model
        try:
            log.info("Loading embedding model: %s", self.config.model_name)
            self._model = SentenceTransformer(self.config.model_name)
        except Exception as exc:
            log.error(
                "Failed to load embedding model '%s': %s. "
                "This may happen on first run without internet access.",
                self.config.model_name, exc,
            )
            return

        # Try loading persisted index first (fast path)
        if self._load_persisted_index():
            self.available = True
            log.info(
                "Loaded persisted FAISS index (%d chunks) from %s",
                len(self._chunks), self.config.index_dir,
            )
            return

        # Slow path: chunk documents and build index
        if not self.documents:
            log.warning(
                "SemanticEngine initialized with empty document set. "
                "Searches will return score 0.0."
            )
            self.available = True
            return

        self._chunks = self._chunk_documents(self.documents)
        if not self._chunks:
            log.warning("No chunks produced from documents. Index will be empty.")
            self.available = True
            return

        self._build_index(self._chunks)
        self._persist_index()
        self.available = True
        log.info(
            "Built and persisted FAISS index: %d chunks from %d documents",
            len(self._chunks), len(self.documents),
        )

    def search(self, prompt: str, top_k: int = 3) -> SemanticResult:
        """
        Embed prompt and search FAISS index for similar chunks.

        Args:
            prompt: Raw user prompt text
            top_k: Number of top chunks to return

        Returns:
            SemanticResult with semantic_score, top_chunks, source_docs
        """
        import numpy as np

        # Handle unavailable engine or empty index
        if not self.available or self._model is None:
            return SemanticResult(
                semantic_score=0.0,
                top_chunks=[],
                source_docs=[],
            )

        if self._index is None or len(self._chunks) == 0:
            return SemanticResult(
                semantic_score=0.0,
                top_chunks=[],
                source_docs=[],
            )

        # Embed the prompt
        try:
            query_embedding = self._model.encode([prompt])
            query_embedding = np.array(query_embedding, dtype=np.float32)

            # Normalize for cosine similarity via inner product
            norm = np.linalg.norm(query_embedding, axis=1, keepdims=True)
            if norm[0][0] > 0:
                query_embedding = query_embedding / norm
        except Exception as exc:
            log.error("Embedding failed for prompt: %s", exc)
            return SemanticResult(
                semantic_score=0.0,
                top_chunks=[],
                source_docs=[],
            )

        # Search FAISS index
        try:
            k = min(top_k, len(self._chunks))
            scores, indices = self._index.search(query_embedding, k)
        except Exception as exc:
            log.error("FAISS search failed: %s", exc)
            return SemanticResult(
                semantic_score=0.0,
                top_chunks=[],
                source_docs=[],
            )

        # Build results
        top_chunks = []
        source_docs_set = set()

        for i in range(len(indices[0])):
            idx = int(indices[0][i])
            score = float(scores[0][i])

            if idx < 0 or idx >= len(self._chunks):
                continue

            chunk = self._chunks[idx]
            # Clamp score to 0.0-1.0
            clamped_score = max(0.0, min(1.0, score))

            top_chunks.append({
                "text": chunk["text"],
                "source_doc": chunk["source_filename"],
                "score": round(clamped_score, 4),
            })
            source_docs_set.add(chunk["source_filename"])

        # semantic_score = max similarity from top-k results
        semantic_score = 0.0
        if top_chunks:
            semantic_score = max(c["score"] for c in top_chunks)

        return SemanticResult(
            semantic_score=round(semantic_score, 4),
            top_chunks=top_chunks,
            source_docs=sorted(source_docs_set),
        )

    def _chunk_documents(self, documents: list[dict]) -> list[dict]:
        """
        Split documents into chunks by heading boundaries or ~chunk_size chars.

        Strategy:
        1. Split on Markdown ## headings first (preserves logical sections)
        2. If a section exceeds chunk_size chars, split further at paragraph
           boundaries (double newline)
        3. Each chunk retains metadata: {text, source_filename, category, heading}
        """
        chunks = []

        for doc in documents:
            content = doc.get("content", "")
            filename = doc.get("filename", "unknown")
            category = doc.get("category", "uncategorized")

            if not content.strip():
                continue

            # Split on ## headings
            sections = re.split(r"(?m)^(##\s+.+)$", content)

            current_heading = ""
            i = 0
            while i < len(sections):
                section_text = sections[i]

                # Check if this is a heading line
                if re.match(r"^##\s+", section_text):
                    current_heading = section_text.strip()
                    i += 1
                    # The content after the heading is the next element
                    if i < len(sections):
                        section_text = sections[i]
                    else:
                        section_text = ""

                # Skip empty sections
                if not section_text.strip():
                    i += 1
                    continue

                # If section is within chunk_size, add as one chunk
                if len(section_text) <= self.config.chunk_size:
                    chunks.append({
                        "text": section_text.strip(),
                        "source_filename": filename,
                        "category": category,
                        "heading": current_heading,
                    })
                else:
                    # Split further at paragraph boundaries
                    paragraphs = re.split(r"\n\n+", section_text)
                    current_chunk = ""

                    for para in paragraphs:
                        para = para.strip()
                        if not para:
                            continue

                        if len(current_chunk) + len(para) + 2 <= self.config.chunk_size:
                            if current_chunk:
                                current_chunk += "\n\n" + para
                            else:
                                current_chunk = para
                        else:
                            # Save current chunk if non-empty
                            if current_chunk:
                                chunks.append({
                                    "text": current_chunk,
                                    "source_filename": filename,
                                    "category": category,
                                    "heading": current_heading,
                                })
                            current_chunk = para

                    # Don't forget the last chunk
                    if current_chunk:
                        chunks.append({
                            "text": current_chunk,
                            "source_filename": filename,
                            "category": category,
                            "heading": current_heading,
                        })

                i += 1

        log.debug("Chunked %d documents into %d chunks", len(documents), len(chunks))
        return chunks

    def _build_index(self, chunks: list[dict]) -> None:
        """
        Embed all chunks and build FAISS IndexFlatIP.

        Normalizes embeddings to unit length so inner-product search
        becomes cosine similarity.
        """
        import faiss
        import numpy as np

        texts = [c["text"] for c in chunks]

        log.info("Embedding %d chunks with model '%s'...", len(texts), self.config.model_name)
        embeddings = self._model.encode(texts, show_progress_bar=False)
        embeddings = np.array(embeddings, dtype=np.float32)

        # Normalize embeddings for cosine similarity via inner product
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        # Avoid division by zero for empty embeddings
        norms = np.maximum(norms, 1e-10)
        embeddings = embeddings / norms

        # Build FAISS inner-product index
        dimension = embeddings.shape[1]
        self._index = faiss.IndexFlatIP(dimension)
        self._index.add(embeddings)

        log.info("FAISS index built: %d vectors, dimension %d", self._index.ntotal, dimension)

    def _load_persisted_index(self) -> bool:
        """
        Load index from disk if mtimes match. Returns True if successful.

        Checks:
        - faiss.index, chunks.json, mtimes.json all exist
        - mtimes of source documents match stored mtimes
        """
        import numpy as np

        index_path = os.path.join(self.config.index_dir, "faiss.index")
        chunks_path = os.path.join(self.config.index_dir, "chunks.json")
        mtimes_path = os.path.join(self.config.index_dir, "mtimes.json")

        # Check all required files exist
        if not all(os.path.exists(p) for p in [index_path, chunks_path, mtimes_path]):
            log.debug("Persisted index files not found, will rebuild.")
            return False

        # Load and compare mtimes
        try:
            with open(mtimes_path, "r", encoding="utf-8") as f:
                stored_mtimes = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Failed to read mtimes.json: %s. Will rebuild.", exc)
            return False

        # Compare current file mtimes against stored
        for doc in self.documents:
            doc_path = doc.get("path", "")
            if not doc_path or not os.path.exists(doc_path):
                log.debug("Document path missing or not found: %s. Will rebuild.", doc_path)
                return False

            current_mtime = os.path.getmtime(doc_path)
            stored_mtime = stored_mtimes.get(doc_path)

            if stored_mtime is None or abs(current_mtime - stored_mtime) > 0.01:
                log.info(
                    "Document modified since last index build: %s. Will rebuild.",
                    doc.get("filename", doc_path),
                )
                return False

        # Check document count matches (catches additions/removals)
        if len(stored_mtimes) != len(self.documents):
            log.info("Document count changed (%d -> %d). Will rebuild.",
                     len(stored_mtimes), len(self.documents))
            return False

        # Load chunks
        try:
            with open(chunks_path, "r", encoding="utf-8") as f:
                self._chunks = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Failed to read chunks.json: %s. Will rebuild.", exc)
            return False

        # Load FAISS index
        try:
            import faiss
            self._index = faiss.read_index(index_path)
        except Exception as exc:
            log.warning(
                "Failed to load faiss.index (possibly corrupted): %s. "
                "Deleting and will rebuild.", exc,
            )
            # Delete corrupted index file
            try:
                os.remove(index_path)
            except OSError:
                pass
            self._chunks = []
            return False

        # Validate index has expected number of vectors
        if self._index.ntotal != len(self._chunks):
            log.warning(
                "Index vector count (%d) != chunk count (%d). Will rebuild.",
                self._index.ntotal, len(self._chunks),
            )
            self._index = None
            self._chunks = []
            return False

        return True

    def _persist_index(self) -> None:
        """
        Save FAISS index, chunks, and mtimes to disk for fast loading
        on subsequent startups.

        Files saved to self.config.index_dir:
        - faiss.index: serialized FAISS IndexFlatIP
        - chunks.json: chunk metadata (text, source, category)
        - mtimes.json: file modification times at index build time
        """
        if self._index is None:
            return

        # Ensure index directory exists
        os.makedirs(self.config.index_dir, exist_ok=True)

        index_path = os.path.join(self.config.index_dir, "faiss.index")
        chunks_path = os.path.join(self.config.index_dir, "chunks.json")
        mtimes_path = os.path.join(self.config.index_dir, "mtimes.json")

        # Save FAISS index
        try:
            import faiss
            faiss.write_index(self._index, index_path)
        except Exception as exc:
            log.error("Failed to persist FAISS index: %s", exc)
            return

        # Save chunks metadata
        try:
            with open(chunks_path, "w", encoding="utf-8") as f:
                json.dump(self._chunks, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            log.error("Failed to persist chunks.json: %s", exc)
            return

        # Save file modification times
        mtimes = {}
        for doc in self.documents:
            doc_path = doc.get("path", "")
            if doc_path and os.path.exists(doc_path):
                mtimes[doc_path] = os.path.getmtime(doc_path)

        try:
            with open(mtimes_path, "w", encoding="utf-8") as f:
                json.dump(mtimes, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            log.error("Failed to persist mtimes.json: %s", exc)
            return

        log.debug("Persisted index to %s", self.config.index_dir)


if __name__ == "__main__":
    # Quick manual test
    from context_loader import load_knowledge_base

    docs = load_knowledge_base()
    engine = SemanticEngine(docs)

    if not engine.available:
        print("SemanticEngine is not available. Check logs above.")
        sys.exit(1)

    test_prompts = [
        "Explain OAuth2.",
        "How does the payment retry flow work?",
        "What is the Orion identity service?",
        "What's the capital of France?",
        "Tell me about the deployment architecture.",
        "",
    ]

    for p in test_prompts:
        result = engine.search(p)
        print(f"\nPrompt: {p!r}")
        print(f"  Semantic Score: {result.semantic_score:.4f}")
        print(f"  Source Docs: {result.source_docs}")
        if result.top_chunks:
            print(f"  Top chunk ({result.top_chunks[0]['score']:.4f}): "
                  f"{result.top_chunks[0]['text'][:80]}...")
