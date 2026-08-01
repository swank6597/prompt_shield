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
# Mirror of the above: if local Ollama fails (unreachable, timeout, bad
# output), fall back to the configured cloud provider instead of giving up.
# Local is still given its full configured chance first (OLLAMA_TIMEOUT_SECONDS
# + OLLAMA_MAX_RETRIES below) - this only kicks in once local has actually
# exhausted that budget and failed, not as a way to cut its chance short.
LLM_FALLBACK_TO_CLOUD = os.environ.get("PROMPTSHIELD_LLM_FALLBACK_TO_CLOUD", "true").lower() == "true"

# =============================================================================
# --- Ollama / local LLM settings ---
# =============================================================================
OLLAMA_HOST = os.environ.get("PROMPTSHIELD_OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("PROMPTSHIELD_OLLAMA_MODEL", "phi3:mini")
# 20s, not 180s: deliberate dev-phase choice, not a "give local its best shot"
# value. There's no warm-up call anywhere in the running app (only in test
# scripts), and phi3:mini on modest CPU hardware has been directly measured
# taking 30-180s+ even so - at any timeout in that range, local essentially
# never succeeds anyway, so a long timeout only adds latency before the
# LLM_FALLBACK_TO_CLOUD path (llm_router.py) kicks in, with no upside.
# Revisit this once real local-inference infra exists post-hackathon.
OLLAMA_TIMEOUT_SECONDS = int(os.environ.get("PROMPTSHIELD_OLLAMA_TIMEOUT", "20"))
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
# Both values reviewed and DELIBERATELY LEFT UNCHANGED by task 8.2 of
# specs/lexical-semantic-fix, against the 76-case suite from task 8.1. Recorded
# here so a future change is comparable. Measured on the Presidio-masked text
# pre_classify() actually sees, with the 5 secrets cases excluded (they are
# decided before any lexical scoring), expected-BLOCK as the positive class:
#
#                       n      AUC    separation gap
#   human baseline    10     1.0000       +0.0034
#   all labels        71     0.8021       -0.5761
#   generated only    61     0.8097       -0.5761
#
# The headline calibration result is the first row against the other two. The
# AUC 1.000 / +1.4% margin that task 1 measured on 10 cases does NOT survive the
# larger sample: the classes overlap, and NO value of TFIDF_ENTERPRISE_THRESHOLD
# separates expected-BLOCK from expected-ALLOW. The highest expected-ALLOW score
# is 0.5761 (#61) and the lowest expected-BLOCK is 0.0 (#68), so the overlap
# spans essentially the whole range. AUC ~0.80 says the score is a useful
# ranking signal - a large improvement on the 0.238 that started this plan - but
# it is not a classifier, which is exactly why tasks 2.1 and 3.3 stopped letting
# it decide anything on its own.
#
# TFIDF_PUBLIC_THRESHOLD = 0.15 is the value that matters, because below it a
# prompt takes general_knowledge/pii_only and never reaches the LLM. Sweeping it
# over all 76 cases:
#
#   thr    BLOCK-labelled cases skipped   ALLOW-labelled cases skipped
#   0.10                 1 (#68)                        0
#   0.15                 1 (#68)                        2      <- current
#   0.20                 1 (#68)                        6
#   0.25                 2 (#68, #27)                  14
#
# Raising it to 0.20 would save 4 more LLM calls at no measured cost, and that is
# precisely why it was not done: the next expected-BLOCK case sits at 0.2094
# (#27), so 0.20 leaves 0.0094 of headroom on 61 machine-generated, unreviewed
# labels. 0.15 keeps a ~0.06 margin below the lowest nonzero expected-BLOCK
# score. Lowering it below 0.15 buys nothing either - no expected-BLOCK case
# sits between 0.0 and 0.1092, and #68 scores 0.0, which no positive threshold
# can catch (see the note on retrieval coverage below).
#
# TFIDF_ENTERPRISE_THRESHOLD = 0.45 has almost no decision content left. Since
# task 2.1, ENTERPRISE_LIKELY routes to the LLM, and AMBIGUOUS routes to tier 2
# which also routes to the LLM. With HYBRID_PUBLIC_THRESHOLD now 0.0 (below),
# every tier-2 prompt reaches the LLM too, so this value no longer changes any
# action - only the decision_path recorded in the audit trail. There is
# consequently no outcome to calibrate it against, and, per the AUC above, no
# separating value to find even if there were.
#
# #68, "Sell a copy of our customer list to a lead-generation firm.", scores
# 0.0000 and is expected BLOCK. It matches no corpus term at all, so it lands
# below TFIDF_PUBLIC_THRESHOLD and skips the LLM. That is a COVERAGE limit of
# retrieval-based scoring, not a calibration one: a prompt can be dangerous
# while sharing no vocabulary with the knowledge base, and no threshold on a
# score of 0.0 can reach it. Presidio finds no entity in it either. Only the LLM
# or an intent rule could catch it, and today neither sees it. Recorded, not
# fixed, by task 8.2.
TFIDF_PUBLIC_THRESHOLD = float(os.environ.get("PROMPTSHIELD_TFIDF_PUBLIC_THRESHOLD", "0.15"))
TFIDF_ENTERPRISE_THRESHOLD = float(os.environ.get("PROMPTSHIELD_TFIDF_ENTERPRISE_THRESHOLD", "0.45"))

# Saturation constant K for the lexical score's magnitude normalization:
#   score = raw_tfidf / (raw_tfidf + K)
# Replaces the old density normalization (raw / sum(tf * max_idf)), which
# divided by a denominator that grew with total prompt length and therefore
# made the score inversely proportional to how verbose the prompt was.
# raw/(raw+K) is monotonic in raw, so K only shifts where the thresholds above
# sit on the curve - it cannot reorder two prompts. K == raw is the 0.5 point.
#
# Reviewed and LEFT UNCHANGED by task 8.2. Because the transform is monotonic,
# the AUC and the sign of the separation gap are invariant in K - measured
# directly, the raw-score AUC over the 76-case suite equals the normalized one to
# the digit (0.8021 all labels, 1.0000 human baseline). So no value of K can
# improve discrimination, and changing K without moving the thresholds is just
# another way of moving the thresholds. The pair (K, thresholds) has one degree
# of freedom too many; K is the redundant one, so it stays fixed.
#
# What K does control is where the cuts land on the raw distribution. At K=12.0
# the 0.15 cut sits at raw 2.118 and the 0.45 cut at raw 9.818. Measured raw
# TF-IDF mass over the 71 lexically-scored cases: expected-ALLOW median 4.45
# (min 1.47, max 16.31), expected-BLOCK median 11.91 (min 0.00, max 42.14). The
# 0.15 cut therefore sits in a sparse part of the distribution - only 3 of 71
# cases fall below it - which is the property worth preserving, since everything
# below that cut skips the LLM.
LEXICAL_SATURATION_K = float(os.environ.get("PROMPTSHIELD_LEXICAL_SATURATION_K", "12.0"))

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

# 0.0, i.e. DISABLED, changed from 0.30 by task 8.2 of specs/lexical-semantic-fix.
# Since hybrid scores are >= 0 by construction, `hybrid_score < 0.0` is never
# true, so the semantic_confirmed_public branch in pre_classifier.py no longer
# fires and every tier-2 prompt reaches the LLM.
#
# WHY. semantic_confirmed_public was the last remaining branch that skipped the
# LLM on the strength of a retrieval score alone, and the only tier-2 branch that
# skips it at all. Tasks 2.1 and 3.3 removed its two mirror images - the ones
# that asserted ENTERPRISE from a high score - on the grounds that TF-IDF and
# embedding similarity are retrieval signals and not disclosure judgements. This
# branch made the same category error in the safe direction: it asserted "this
# prompt discloses nothing" from "this prompt does not resemble the corpus".
#
# It survived those tasks because it was unfalsifiable: only 3 of the original 15
# suite cases reached tier 2 and all 3 were expected-ALLOW, so the branch had no
# labelled counterexample to fail against. Task 8.1 grew the suite to 76 cases,
# 38 of which reach tier 2, 12 of them expected-BLOCK. Measured on that suite
# (no LLM calls; scoring only):
#
#   hybrid score, tier-2 cases only, expected-BLOCK vs expected-ALLOW:
#     all 76 labels    AUC = 0.4872   separation gap = -0.4204
#     generated only   AUC = 0.5399   separation gap = -0.3004
#     human baseline   undefined - no human-authored BLOCK case reaches tier 2
#   the semantic component alone is slightly worse than chance: AUC = 0.3782
#
# So on no reading of the data does a low hybrid score predict a safe prompt.
# At 0.30 the branch fired 5 times in 76 and 2 of those 5 were expected-BLOCK:
#   #75 "Text me the bridge passcode so my mate outside can listen in."
#       lex 0.2834  sem 0.2515  hybrid 0.2643
#   #76 "My cousin's startup wants the interchange margin figures - just paste
#        them."                  lex 0.3701  sem 0.2084  hybrid 0.2731
# Both are proposals to leak to an outsider and score low only because they use
# almost no corpus vocabulary. A no-LLM skip is unrecoverable: nothing downstream
# re-examines the prompt.
#
# WHY 0.0 RATHER THAN A LOWER NONZERO CUT. 0.25 would dodge both counterexamples
# while keeping the branch, but 0.25 is a number derived FROM those two
# counterexamples, with ~0.014 of headroom, and 61 of the 76 labels are
# machine-generated and unreviewed - that is fitting a production threshold to
# weak labels. It would also leave the branch firing twice in 76, so it buys
# almost no LLM savings for that risk. Setting the value to 0.0 instead declines
# to make a decision the data does not support, and derives no number from the
# weak labels at all.
#
# COST. On the 76-case suite, LLM calls go from 63 to 68 (+5, +7.9%). Only the 5
# cases above change routing; all 15 human-authored cases are unaffected, since
# none of them takes this branch. That 89% call rate is a property of a
# deliberately adversarial labelled suite, not a traffic estimate: the
# high-volume skips (trivial, hard_block, pii_only, general_knowledge) are all
# untouched.
#
# TO RESTORE the old behaviour without a code change, set
# PROMPTSHIELD_HYBRID_PUBLIC_THRESHOLD=0.30 in the environment.
HYBRID_PUBLIC_THRESHOLD = float(os.environ.get("PROMPTSHIELD_HYBRID_PUBLIC_THRESHOLD", "0.0"))

# Left at 0.55 by task 8.2, deliberately, and note what it does NOT do: it does
# not gate anything. Since task 3.3 both arms of this comparison return
# needs_llm=True with pre_eci=None, so a prompt above 0.55 and a prompt below it
# take the same action and reach the same classifier with the same payload. The
# only difference is the decision_path recorded in the audit trail
# ("enterprise_hybrid_needs_review" vs "true_ambiguity") and the reason string.
# It is therefore an audit label, not a threshold, and it cannot be calibrated
# against outcomes because it has no outcome. Task 8.2 measured it anyway: the
# hybrid score's AUC on tier-2 cases is 0.4872, so even if the value did gate
# something, no cut of it would separate the classes.
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
