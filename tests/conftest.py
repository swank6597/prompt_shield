"""
Shared test fixtures and Hypothesis strategies for the lexical-semantic-upgrade test suite.

Provides:
- Path setup so all tests can import from backend/ai
- Hypothesis strategies for test corpus generation
- Pytest fixtures for mock Presidio results and configuration defaults
- Optional session-scoped FAISS index fixture for semantic engine tests

Requirements: 10.1, 10.2, 10.3
"""

import sys
import os

# ---------------------------------------------------------------------------
# Path setup: ensure backend/ and backend/ai/ are importable from all tests
# ---------------------------------------------------------------------------
_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "backend"))
_AI_DIR = os.path.join(_BACKEND_DIR, "ai")
for _d in (_BACKEND_DIR, _AI_DIR):
    if _d not in sys.path:
        sys.path.insert(0, _d)

import pytest
from hypothesis import strategies as st


# ===========================================================================
# Hypothesis strategies for test corpus generation
# ===========================================================================

@st.composite
def knowledge_base_documents(draw, min_docs=1, max_docs=10):
    """
    Strategy: generates a list of knowledge base document dicts matching the
    format returned by context_loader.load_knowledge_base().

    Each dict has keys: path, filename, category, content
    """
    categories = ["apis", "security", "infrastructure", "internal", "uncategorized"]
    num_docs = draw(st.integers(min_value=min_docs, max_value=max_docs))
    documents = []
    for i in range(num_docs):
        category = draw(st.sampled_from(categories))
        filename = draw(
            st.from_regex(r"[a-z][a-z0-9\-]{2,20}\.md", fullmatch=True)
        )
        content = draw(st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "S", "Zs"),
                blacklist_characters="\x00",
            ),
            min_size=10,
            max_size=500,
        ))
        documents.append({
            "path": f"knowledge/{category}/{filename}",
            "filename": filename,
            "category": category,
            "content": content,
        })
    return documents


@st.composite
def semantic_chunks(draw, min_chunks=1, max_chunks=5):
    """
    Strategy: generates a list of semantic chunk dicts matching the format
    returned by SemanticEngine.search().

    Each dict has keys: text, source_doc, score
    """
    num_chunks = draw(st.integers(min_value=min_chunks, max_value=max_chunks))
    chunks = []
    for _ in range(num_chunks):
        text = draw(st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "S", "Zs"),
                blacklist_characters="\x00",
            ),
            min_size=5,
            max_size=300,
        ))
        source_doc = draw(
            st.from_regex(r"[a-z][a-z0-9\-]{2,15}\.md", fullmatch=True)
        )
        score = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))
        chunks.append({
            "text": text,
            "source_doc": source_doc,
            "score": score,
        })
    # Sort by descending score (matching real engine behavior)
    chunks.sort(key=lambda c: c["score"], reverse=True)
    return chunks


def random_prompts():
    """
    Strategy: generates random text strings of various lengths suitable for
    testing prompt processing pipelines.
    """
    return st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N", "P", "S", "Zs"),
            blacklist_characters="\x00",
        ),
        min_size=0,
        max_size=500,
    )


# ===========================================================================
# Pytest fixtures
# ===========================================================================

@pytest.fixture
def sample_documents():
    """
    Returns a small fixed set of knowledge base documents (5 docs) for
    deterministic unit tests.
    """
    return [
        {
            "path": "knowledge/apis/Identity-api.md",
            "filename": "Identity-api.md",
            "category": "apis",
            "content": (
                "## OAuth2 Implementation\n\n"
                "The Orion identity service uses OAuth2 with PKCE flow for all "
                "client applications. Tokens expire after 3600 seconds.\n\n"
                "## Token Refresh\n\n"
                "Refresh tokens are rotated on each use. The identity service "
                "endpoint is /api/v2/auth/token."
            ),
        },
        {
            "path": "knowledge/apis/payment-api.md",
            "filename": "payment-api.md",
            "category": "apis",
            "content": (
                "## Payment Processing\n\n"
                "The Mercury payment gateway processes transactions via "
                "the /api/v1/payments endpoint. Settlement occurs daily at UTC midnight.\n\n"
                "## Refund Policy\n\n"
                "Refunds must be initiated within 30 days of the original transaction."
            ),
        },
        {
            "path": "knowledge/security/access-control.md",
            "filename": "access-control.md",
            "category": "security",
            "content": (
                "## Role-Based Access Control\n\n"
                "The RBAC system uses three tiers: viewer, editor, and admin. "
                "Admin access requires multi-factor authentication via the Orion SSO.\n\n"
                "## API Key Management\n\n"
                "API keys are scoped per-service and rotated every 90 days."
            ),
        },
        {
            "path": "knowledge/infrastructure/deployment.md",
            "filename": "deployment.md",
            "category": "infrastructure",
            "content": (
                "## CI/CD Pipeline\n\n"
                "Deployments use GitHub Actions with a blue-green strategy. "
                "Rollback is automated if health checks fail within 5 minutes.\n\n"
                "## Scaling Policy\n\n"
                "Auto-scaling triggers at 70% CPU utilization across the cluster."
            ),
        },
        {
            "path": "knowledge/internal/onboarding.md",
            "filename": "onboarding.md",
            "category": "internal",
            "content": (
                "## New Employee Setup\n\n"
                "All new hires receive access to the internal wiki and Slack channels "
                "on day one. VPN credentials are provisioned by IT within 24 hours."
            ),
        },
    ]


@pytest.fixture
def mock_presidio_no_entities():
    """
    Returns a Presidio result dict with no detected entities.
    Suitable for testing routing paths that expect clean input.
    """
    return {
        "entityCount": 0,
        "maskedText": "What is the weather like today?",
        "entities": [],
    }


@pytest.fixture
def mock_presidio_with_pii():
    """
    Returns a Presidio result dict with PII entities (PERSON, EMAIL_ADDRESS).
    Suitable for testing the pii_only routing path.
    """
    return {
        "entityCount": 2,
        "maskedText": "Please contact <PERSON> at <EMAIL_ADDRESS> for details.",
        "entities": [
            {
                "type": "PERSON",
                "text": "John Smith",
                "score": 0.95,
                "start": 15,
                "end": 25,
            },
            {
                "type": "EMAIL_ADDRESS",
                "text": "john.smith@company.com",
                "score": 0.99,
                "start": 29,
                "end": 51,
            },
        ],
    }


@pytest.fixture
def mock_presidio_with_secrets():
    """
    Returns a Presidio result dict with secret entities (GITHUB_TOKEN).
    Suitable for testing the hard_block routing path.
    """
    return {
        "entityCount": 1,
        "maskedText": "My token is <GITHUB_TOKEN>",
        "entities": [
            {
                "type": "GITHUB_TOKEN",
                "text": "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                "score": 0.98,
                "start": 12,
                "end": 52,
            },
        ],
    }


@pytest.fixture
def config_defaults(monkeypatch):
    """
    Ensures config values are at their defaults for the duration of the test,
    then resets after. Use when a test needs guaranteed default configuration.

    Usage: include `config_defaults` as a parameter in your test function.
    """
    import config

    # Store originals
    originals = {
        "TFIDF_PUBLIC_THRESHOLD": config.TFIDF_PUBLIC_THRESHOLD,
        "TFIDF_ENTERPRISE_THRESHOLD": config.TFIDF_ENTERPRISE_THRESHOLD,
        "EMBEDDING_MODEL": config.EMBEDDING_MODEL,
        "SEMANTIC_CHUNK_SIZE": config.SEMANTIC_CHUNK_SIZE,
        "HYBRID_LEXICAL_WEIGHT": config.HYBRID_LEXICAL_WEIGHT,
        "HYBRID_SEMANTIC_WEIGHT": config.HYBRID_SEMANTIC_WEIGHT,
        "HYBRID_PUBLIC_THRESHOLD": config.HYBRID_PUBLIC_THRESHOLD,
        "HYBRID_ENTERPRISE_THRESHOLD": config.HYBRID_ENTERPRISE_THRESHOLD,
        "USE_LEGACY_SEARCH": config.USE_LEGACY_SEARCH,
    }

    # Set defaults
    monkeypatch.setattr(config, "TFIDF_PUBLIC_THRESHOLD", 0.15)
    monkeypatch.setattr(config, "TFIDF_ENTERPRISE_THRESHOLD", 0.45)
    monkeypatch.setattr(config, "EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    monkeypatch.setattr(config, "SEMANTIC_CHUNK_SIZE", 500)
    monkeypatch.setattr(config, "HYBRID_LEXICAL_WEIGHT", 0.4)
    monkeypatch.setattr(config, "HYBRID_SEMANTIC_WEIGHT", 0.6)
    monkeypatch.setattr(config, "HYBRID_PUBLIC_THRESHOLD", 0.30)
    monkeypatch.setattr(config, "HYBRID_ENTERPRISE_THRESHOLD", 0.55)
    monkeypatch.setattr(config, "USE_LEGACY_SEARCH", False)

    yield config

    # monkeypatch handles restoration automatically


# ===========================================================================
# Small FAISS index fixture (session-scoped, optional)
# ===========================================================================

@pytest.fixture(scope="session")
def small_faiss_index(tmp_path_factory):
    """
    Attempts to build a tiny FAISS index from sample documents using
    sentence-transformers. Yields the (index, chunks, model) tuple if
    available, or None if sentence-transformers/faiss are not installed.

    Session-scoped to avoid expensive re-computation across tests.
    """
    try:
        import numpy as np
        faiss = pytest.importorskip("faiss", reason="faiss-cpu not installed")
        SentenceTransformer = pytest.importorskip(
            "sentence_transformers",
            reason="sentence-transformers not installed",
        )
        from sentence_transformers import SentenceTransformer as ST
    except Exception:
        yield None
        return

    try:
        # Use a small set of chunks for the test index
        chunks = [
            {"text": "OAuth2 implementation with PKCE flow for client apps", "source_filename": "Identity-api.md", "category": "apis"},
            {"text": "Mercury payment gateway processes transactions daily", "source_filename": "payment-api.md", "category": "apis"},
            {"text": "Role-based access control with three tiers of permissions", "source_filename": "access-control.md", "category": "security"},
            {"text": "GitHub Actions CI/CD pipeline with blue-green deployments", "source_filename": "deployment.md", "category": "infrastructure"},
            {"text": "New employee onboarding setup for wiki and Slack access", "source_filename": "onboarding.md", "category": "internal"},
        ]

        # Load model (will use cached version if available)
        model = ST("all-MiniLM-L6-v2")

        # Embed chunks
        texts = [c["text"] for c in chunks]
        embeddings = model.encode(texts, normalize_embeddings=True)
        embeddings = np.array(embeddings, dtype=np.float32)

        # Build FAISS index
        dim = embeddings.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(embeddings)

        yield {"index": index, "chunks": chunks, "model": model, "dim": dim}

    except Exception:
        # Model download failure or other issue - gracefully degrade
        yield None
