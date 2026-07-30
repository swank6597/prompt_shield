# config.py
# Centralized configuration loaded from backend/.env file (never committed).
# Falls back to environment variables, then sensible defaults.
#
# Priority order: .env file -> OS environment variable -> default value
#
# To add a new provider or setting:
#   1. Add the key to .env.example (with placeholder value)
#   2. Add the key to your local .env (with real value)
#   3. Add the os.environ.get() line here

import os
from pathlib import Path

# Load .env file BEFORE reading any os.environ values. This makes the
# .env file the single source of truth for local dev, while still
# allowing actual env vars (e.g. in Docker/CI) to override.
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).parent / ".env"
    load_dotenv(_env_path, override=False)  # override=False: real env vars win
except ImportError:
    # python-dotenv not installed - rely on real environment variables only.
    # This is fine in production (Docker, CI) where secrets come from the
    # orchestrator's env injection, not a file.
    pass

# =============================================================================
# --- Smart LLM Router settings ---
# =============================================================================
# Strategies: "local" | "cloud" | "auto"
#   local  -> Always use local Ollama (original behavior)
#   cloud  -> Always use the configured cloud provider
#   auto   -> Pick per-request based on prompt complexity/length
LLM_STRATEGY = os.environ.get("PROMPTSHIELD_LLM_STRATEGY", "local")

# Cloud provider: "groq" | "bedrock" | "gemini"
LLM_CLOUD_PROVIDER = os.environ.get("PROMPTSHIELD_LLM_CLOUD_PROVIDER", "groq")

# --- Auto-routing thresholds ---
LLM_AUTO_LENGTH_THRESHOLD = int(os.environ.get("PROMPTSHIELD_LLM_AUTO_LENGTH_THRESHOLD", "50"))
LLM_AUTO_ENTITY_THRESHOLD = int(os.environ.get("PROMPTSHIELD_LLM_AUTO_ENTITY_THRESHOLD", "3"))

# --- Fallback behavior ---
LLM_FALLBACK_TO_LOCAL = os.environ.get("PROMPTSHIELD_LLM_FALLBACK_TO_LOCAL", "true").lower() == "true"

# =============================================================================
# --- Ollama / local LLM settings ---
# =============================================================================
OLLAMA_HOST = os.environ.get("PROMPTSHIELD_OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("PROMPTSHIELD_OLLAMA_MODEL", "phi3:mini")
OLLAMA_TIMEOUT_SECONDS = int(os.environ.get("PROMPTSHIELD_OLLAMA_TIMEOUT", "180"))
OLLAMA_MAX_RETRIES = int(os.environ.get("PROMPTSHIELD_OLLAMA_MAX_RETRIES", "1"))

# =============================================================================
# --- Groq settings (free tier: llama-3.1-8b-instant, 30 req/min) ---
# =============================================================================
GROQ_API_KEY = os.environ.get("PROMPTSHIELD_GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("PROMPTSHIELD_GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_TIMEOUT_SECONDS = int(os.environ.get("PROMPTSHIELD_GROQ_TIMEOUT", "30"))

# =============================================================================
# --- Google Gemini settings (free tier: 15 req/min) ---
# =============================================================================
GEMINI_API_KEY = os.environ.get("PROMPTSHIELD_GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("PROMPTSHIELD_GEMINI_MODEL", "gemini-2.0-flash-lite")
GEMINI_TIMEOUT_SECONDS = int(os.environ.get("PROMPTSHIELD_GEMINI_TIMEOUT", "30"))

# =============================================================================
# --- Amazon Bedrock settings ---
# =============================================================================
BEDROCK_REGION = os.environ.get("PROMPTSHIELD_BEDROCK_REGION", "us-east-1")
BEDROCK_MODEL_ID = os.environ.get(
    "PROMPTSHIELD_BEDROCK_MODEL_ID",
    "anthropic.claude-3-haiku-20240307-v1:0"
)
BEDROCK_TIMEOUT_SECONDS = int(os.environ.get("PROMPTSHIELD_BEDROCK_TIMEOUT", "30"))

# =============================================================================
# --- Presidio settings ---
# =============================================================================
PRESIDIO_MIN_SCORE = float(os.environ.get("PROMPTSHIELD_PRESIDIO_MIN_SCORE", "0.85"))

# =============================================================================
# --- Lexical Engine (TF-IDF) settings ---
# =============================================================================
TFIDF_PUBLIC_THRESHOLD = float(os.environ.get("PROMPTSHIELD_TFIDF_PUBLIC_THRESHOLD", "0.15"))
TFIDF_ENTERPRISE_THRESHOLD = float(os.environ.get("PROMPTSHIELD_TFIDF_ENTERPRISE_THRESHOLD", "0.45"))

# =============================================================================
# --- Semantic Engine settings ---
# =============================================================================
EMBEDDING_MODEL = os.environ.get("PROMPTSHIELD_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
SEMANTIC_CHUNK_SIZE = int(os.environ.get("PROMPTSHIELD_SEMANTIC_CHUNK_SIZE", "500"))

# =============================================================================
# --- Hybrid Scoring settings ---
# =============================================================================
HYBRID_LEXICAL_WEIGHT = float(os.environ.get("PROMPTSHIELD_HYBRID_LEXICAL_WEIGHT", "0.4"))
HYBRID_SEMANTIC_WEIGHT = float(os.environ.get("PROMPTSHIELD_HYBRID_SEMANTIC_WEIGHT", "0.6"))
HYBRID_PUBLIC_THRESHOLD = float(os.environ.get("PROMPTSHIELD_HYBRID_PUBLIC_THRESHOLD", "0.30"))
HYBRID_ENTERPRISE_THRESHOLD = float(os.environ.get("PROMPTSHIELD_HYBRID_ENTERPRISE_THRESHOLD", "0.55"))

# =============================================================================
# --- Legacy fallback ---
# =============================================================================
USE_LEGACY_SEARCH = os.environ.get("PROMPTSHIELD_USE_LEGACY_SEARCH", "false").lower() == "true"

# =============================================================================
# --- Audit log settings (see backend/audit/README.md) ---
# =============================================================================
# SQLite file backing the audit trail. Colocated with the module by default;
# override for a shared location (e.g. a mounted volume) without a code change.
AUDIT_DB_PATH = os.environ.get(
    "PROMPTSHIELD_AUDIT_DB_PATH",
    os.path.join(os.path.dirname(__file__), "audit", "audit_log.db"),
)

# =============================================================================
# --- Authentication settings (see specs/authentication/) ---
# =============================================================================
# Secret used to sign Access_Tokens (JWT, HS256). No safe default - left empty
# so backend/auth/security.py can fail loudly at import time instead of
# silently signing tokens with a well-known key. Generate one with:
#   python -c "import secrets; print(secrets.token_urlsafe(32))"
AUTH_SECRET_KEY = os.environ.get("PROMPTSHIELD_AUTH_SECRET_KEY", "")

# Access token lifetime in minutes.
AUTH_TOKEN_EXPIRE_MINUTES = int(os.environ.get("PROMPTSHIELD_AUTH_TOKEN_EXPIRE_MINUTES", "60"))

# bcrypt work factor for password/API-key hashing.
AUTH_BCRYPT_ROUNDS = int(os.environ.get("PROMPTSHIELD_AUTH_BCRYPT_ROUNDS", "12"))

# Minimum plaintext password length accepted at account creation.
AUTH_MIN_PASSWORD_LENGTH = int(os.environ.get("PROMPTSHIELD_AUTH_MIN_PASSWORD_LENGTH", "8"))

# Login lockout: after this many consecutive failed attempts, the account is
# locked for AUTH_LOGIN_LOCKOUT_MINUTES.
AUTH_LOGIN_MAX_ATTEMPTS = int(os.environ.get("PROMPTSHIELD_AUTH_LOGIN_MAX_ATTEMPTS", "5"))
AUTH_LOGIN_LOCKOUT_MINUTES = int(os.environ.get("PROMPTSHIELD_AUTH_LOGIN_LOCKOUT_MINUTES", "15"))

# SQLite file for users/devices/auth_audit_log (git-ignored, created on first run).
AUTH_DB_PATH = os.environ.get(
    "PROMPTSHIELD_AUTH_DB_PATH",
    str(Path(__file__).parent / "auth" / "auth.db"),
)

# CORS origins allowed to call /auth/* and /devices/* - deliberately NOT the
# same wildcard as /api/scan (Requirement 8.1 in specs/authentication/):
# those routes expose login/audit/device-management, a more sensitive
# surface than a stateless scan call. Empty by default since no real
# dashboard origin exists yet; comma-separated list, e.g.
# "https://dashboard.internal.example.com,http://localhost:5173".
AUTH_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("PROMPTSHIELD_AUTH_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]
