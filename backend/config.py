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
GEMINI_MODEL = os.environ.get("PROMPTSHIELD_GEMINI_MODEL", "gemini-2.0-flash")
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
