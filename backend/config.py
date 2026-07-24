# config.py
# Centralized configuration: Ollama host/model name, timeouts, and other
# environment-driven settings. Reads from environment variables with
# sensible defaults, so hardware-specific tuning (e.g. a lighter model
# for local dev on modest laptops) never requires a code change.

import os

# --- Ollama / ECI settings ---
OLLAMA_HOST = os.environ.get("PROMPTSHIELD_OLLAMA_HOST", "http://localhost:11434")

# Default is phi3:mini (intended hackathon-day model). For local dev on
# modest hardware (e.g. a 4-core laptop CPU with 8GB RAM), swap to a
# much smaller/faster model by setting an environment variable instead
# of editing this file, e.g.:
#   Windows (PowerShell):  $env:PROMPTSHIELD_OLLAMA_MODEL = "qwen2.5:0.5b-instruct"
#   macOS/Linux:           export PROMPTSHIELD_OLLAMA_MODEL=qwen2.5:0.5b-instruct
# Remember to pull whatever model you set: `ollama pull qwen2.5:0.5b-instruct`
OLLAMA_MODEL = os.environ.get("PROMPTSHIELD_OLLAMA_MODEL", "phi3:mini")

OLLAMA_TIMEOUT_SECONDS = int(os.environ.get("PROMPTSHIELD_OLLAMA_TIMEOUT", "180"))
OLLAMA_MAX_RETRIES = int(os.environ.get("PROMPTSHIELD_OLLAMA_MAX_RETRIES", "1"))

# --- Presidio settings ---
PRESIDIO_MIN_SCORE = float(os.environ.get("PROMPTSHIELD_PRESIDIO_MIN_SCORE", "0.85"))

# --- Audit log settings ---
# SQLite file backing the audit trail (backend/audit/audit_logger.py).
# Colocated with the module by default; override for a shared location
# (e.g. a mounted volume) without a code change.
AUDIT_DB_PATH = os.environ.get(
    "PROMPTSHIELD_AUDIT_DB_PATH",
    os.path.join(os.path.dirname(__file__), "audit", "audit_log.db"),
)