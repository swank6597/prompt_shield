# pre_classifier.py
# Deterministic pre-classifier that decides whether an LLM call is needed.
#
# The goal: AVOID expensive LLM calls when cheaper signals already give
# a definitive answer. This saves tokens, money, and 10-20s of latency.
#
# Three-tier routing decision (post-upgrade):
#
#   TIER 0 (unchanged):
#     Trivial prompt + no entities -> SKIP (trivial)
#     Secrets detected -> SKIP (hard_block) — ALWAYS takes priority
#
#   TIER 1 — Lexical (TF-IDF):
#     PII + PUBLIC verdict -> SKIP (pii_only)
#     PUBLIC verdict, no PII -> SKIP (general_knowledge)
#     ENTERPRISE_LIKELY verdict -> SKIP (enterprise_detected)
#     AMBIGUOUS verdict -> proceed to Tier 2
#
#   TIER 2 — Semantic (hybrid scoring):
#     hybrid_score < 0.30 -> SKIP (semantic_confirmed_public)
#     hybrid_score >= 0.55 -> SKIP (semantic_confirmed_enterprise)
#     0.30 <= hybrid_score < 0.55 -> NEEDS LLM (true_ambiguity)
#
# Note: skipping the LLM here means the resulting ECI's `confidence` is not
# a flat constant - _build_enterprise_eci() scales it by how far the
# triggering score clears its threshold, so a score that only just crosses
# ENTERPRISE_LIKELY/hybrid-enterprise (e.g. from a couple of weak/generic
# matched terms) lands below policy_engine's block_internal_architecture_or_code
# eci_min_confidence=0.7 gate and falls through to WARN instead of BLOCK.
#
# Priority order: secrets > PII+PUBLIC > lexical verdict > semantic hybrid
#
# Graceful degradation:
#   - If LexicalEngine unavailable: fall through to LLM
#   - If SemanticEngine unavailable: treat AMBIGUOUS as -> LLM
#   - If both unavailable: revert to pre-upgrade behavior (PII/secrets/trivial only)

import os
import sys

_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_AI_DIR = os.path.dirname(__file__)
for _d in (_BACKEND_DIR, _AI_DIR):
    if _d not in sys.path:
        sys.path.insert(0, _d)

import config  # noqa: E402
from keyword_search import search as keyword_search  # noqa: E402
from utils.helpers import is_trivial_prompt  # noqa: E402
from utils.logger import get_logger  # noqa: E402

log = get_logger("pre_classifier")

# ─── Graceful imports for new engines ────────────────────────────────────────
_lexical_engine_instance = None
_semantic_engine_instance = None
_lexical_available = False
_semantic_available = False

try:
    from lexical_engine import LexicalEngine, LexicalResult  # noqa: E402
    from context_loader import load_knowledge_base  # noqa: E402

    if not config.USE_LEGACY_SEARCH:
        _docs = load_knowledge_base()
        _lexical_engine_instance = LexicalEngine(_docs)
        _lexical_available = True
        log.info("LexicalEngine initialized successfully (%d docs)", len(_docs))
except Exception as exc:
    log.warning(
        "LexicalEngine unavailable: %s. Will fall through to LLM for non-trivial prompts.",
        exc,
    )
    _lexical_available = False

try:
    from semantic_engine import SemanticEngine, SemanticResult  # noqa: E402
    if not config.USE_LEGACY_SEARCH:
        # Reuse docs from lexical init, or load fresh
        if '_docs' not in dir() or _docs is None:
            from context_loader import load_knowledge_base  # noqa: E402
            _docs = load_knowledge_base()
        _semantic_engine_instance = SemanticEngine(_docs)
        if _semantic_engine_instance.available:
            _semantic_available = True
            log.info("SemanticEngine initialized successfully")
        else:
            _semantic_available = False
            log.warning("SemanticEngine loaded but marked unavailable (missing deps?)")
except Exception as exc:
    log.warning(
        "SemanticEngine unavailable: %s. AMBIGUOUS verdicts will route to LLM.",
        exc,
    )
    _semantic_available = False

# ─── Constants ────────────────────────────────────────────────────────────────

# Entity types that indicate secrets/credentials - if Presidio catches these,
# the policy engine will BLOCK regardless of what the LLM says.
_SECRET_ENTITY_TYPES = {
    "GITHUB_TOKEN", "OPENAI_API_KEY", "AWS_ACCESS_KEY",
    "AWS_SECRET_KEY", "PRIVATE_KEY", "JWT_TOKEN",
}

# Minimum keyword search score to consider a prompt "enterprise-relevant"
# enough to warrant an LLM call. (Legacy mode only)
_ENTERPRISE_RELEVANCE_THRESHOLD = 3


def pre_classify(prompt: str, masked_text: str, presidio_result: dict) -> dict:
    """
    Deterministic pre-classification gate. Decides whether the LLM is needed.

    Args:
        prompt: Original user prompt (for trivial detection).
        masked_text: Prompt after Presidio masking.
        presidio_result: Dict from presidio_engine.analyze_text() with
                         keys: entityCount, maskedText, entities.

    Returns a dict:
        {
            "needs_llm": bool,            # True = must call LLM, False = skip it
            "reason": str,                # Human-readable explanation
            "decision_path": str,         # Machine-readable path taken
            "pre_eci": dict | None,       # Pre-filled ECI result if LLM skipped
            "knowledge_hits": list,       # Top keyword search matches (for reuse)
            "lexical_result": dict | None,   # LexicalResult as dict (NEW)
            "semantic_result": dict | None,  # SemanticResult as dict (NEW)
            "hybrid_score": float | None,    # Hybrid score (NEW)
        }
    """
    entity_count = presidio_result["entityCount"]
    entity_types = {e["entity_type"] for e in presidio_result["entities"]}

    # =========================================================================
    # PATH 1: Trivial prompt + no entities -> definitely safe, skip LLM
    # =========================================================================
    if entity_count == 0 and is_trivial_prompt(prompt):
        log.info("Pre-classifier: SKIP (trivial prompt, no entities)")
        return {
            "needs_llm": False,
            "reason": "Trivial prompt with no sensitive data",
            "decision_path": "trivial",
            "pre_eci": _build_safe_eci("Trivial prompt, no enterprise relevance"),
            "knowledge_hits": [],
            "lexical_result": None,
            "semantic_result": None,
            "hybrid_score": None,
        }

    # =========================================================================
    # PATH 2: Secrets detected -> policy will BLOCK, LLM adds nothing
    # (ALWAYS takes priority over everything else)
    # =========================================================================
    detected_secrets = entity_types & _SECRET_ENTITY_TYPES
    if detected_secrets:
        log.info(
            "Pre-classifier: SKIP (secrets detected: %s, policy will BLOCK)",
            sorted(detected_secrets),
        )
        return {
            "needs_llm": False,
            "reason": f"Credentials detected ({', '.join(sorted(detected_secrets))}), policy will block",
            "decision_path": "hard_block",
            "pre_eci": _build_secrets_eci(detected_secrets, entity_types),
            "knowledge_hits": [],
            "lexical_result": None,
            "semantic_result": None,
            "hybrid_score": None,
        }

    # =========================================================================
    # LEGACY MODE: use existing keyword_search if USE_LEGACY_SEARCH is true
    # =========================================================================
    if config.USE_LEGACY_SEARCH:
        return _legacy_classify(prompt, masked_text, entity_count, entity_types)

    # =========================================================================
    # THREE-TIER ROUTING (new engines)
    # =========================================================================

    # Check if lexical engine is available; if not, degrade to LLM
    if not _lexical_available or _lexical_engine_instance is None:
        log.warning(
            "Pre-classifier: LexicalEngine unavailable, degrading to LLM for non-trivial prompt"
        )
        return {
            "needs_llm": True,
            "reason": "Lexical engine unavailable, sending to LLM as fallback",
            "decision_path": "engine_degraded",
            "pre_eci": None,
            "knowledge_hits": [],
            "lexical_result": None,
            "semantic_result": None,
            "hybrid_score": None,
        }

    # ─── TIER 1: Lexical Engine scoring ─────────────────────────────────────
    lexical_result = _lexical_engine_instance.score(masked_text)
    lexical_dict = {
        "tfidf_score": lexical_result.tfidf_score,
        "verdict": lexical_result.verdict,
        "top_docs": lexical_result.top_docs,
        "matched_terms": lexical_result.matched_terms,
    }

    # Build knowledge_hits for backward compatibility (same shape as keyword_search)
    knowledge_hits = [
        {"filename": d["filename"], "score": d["score"]}
        for d in lexical_result.top_docs
    ]

    # ─── PII + PUBLIC verdict -> pii_only ────────────────────────────────────
    if entity_count > 0 and lexical_result.verdict == "PUBLIC":
        log.info(
            "Pre-classifier: SKIP (PII only + PUBLIC lexical verdict, tfidf=%.4f)",
            lexical_result.tfidf_score,
        )
        return {
            "needs_llm": False,
            "reason": "PII detected but lexical verdict is PUBLIC (no enterprise context)",
            "decision_path": "pii_only",
            "pre_eci": _build_pii_only_eci(entity_types),
            "knowledge_hits": knowledge_hits,
            "lexical_result": lexical_dict,
            "semantic_result": None,
            "hybrid_score": None,
        }

    # ─── PUBLIC verdict, no PII -> general_knowledge ─────────────────────────
    if entity_count == 0 and lexical_result.verdict == "PUBLIC":
        log.info(
            "Pre-classifier: SKIP (general_knowledge, tfidf=%.4f)",
            lexical_result.tfidf_score,
        )
        return {
            "needs_llm": False,
            "reason": "General knowledge prompt, no enterprise relevance (lexical PUBLIC)",
            "decision_path": "general_knowledge",
            "pre_eci": _build_safe_eci("Lexical verdict PUBLIC, no enterprise overlap"),
            "knowledge_hits": knowledge_hits,
            "lexical_result": lexical_dict,
            "semantic_result": None,
            "hybrid_score": None,
        }

    # ─── ENTERPRISE_LIKELY verdict -> enterprise_detected ────────────────────
    if lexical_result.verdict == "ENTERPRISE_LIKELY":
        log.info(
            "Pre-classifier: SKIP (enterprise_detected, tfidf=%.4f, terms=%s)",
            lexical_result.tfidf_score,
            lexical_result.matched_terms[:5],
        )
        return {
            "needs_llm": False,
            "reason": f"Enterprise context detected via TF-IDF (score={lexical_result.tfidf_score:.4f})",
            "decision_path": "enterprise_detected",
            "pre_eci": _build_enterprise_eci(lexical_result),
            "knowledge_hits": knowledge_hits,
            "lexical_result": lexical_dict,
            "semantic_result": None,
            "hybrid_score": None,
        }

    # ─── AMBIGUOUS verdict -> proceed to Tier 2 (semantic) ───────────────────
    # If semantic engine is unavailable, treat AMBIGUOUS as -> LLM
    if not _semantic_available or _semantic_engine_instance is None:
        log.info(
            "Pre-classifier: NEEDS LLM (AMBIGUOUS verdict but SemanticEngine unavailable, "
            "tfidf=%.4f)",
            lexical_result.tfidf_score,
        )
        return {
            "needs_llm": True,
            "reason": "Lexical verdict AMBIGUOUS, semantic engine unavailable, routing to LLM",
            "decision_path": "true_ambiguity",
            "pre_eci": None,
            "knowledge_hits": knowledge_hits,
            "lexical_result": lexical_dict,
            "semantic_result": None,
            "hybrid_score": None,
        }

    # ─── TIER 2: Semantic Engine + Hybrid Scoring ────────────────────────────
    semantic_result = _semantic_engine_instance.search(prompt)
    semantic_dict = {
        "semantic_score": semantic_result.semantic_score,
        "top_chunks": semantic_result.top_chunks,
        "source_docs": semantic_result.source_docs,
    }

    # Compute hybrid score: weighted combination of lexical and semantic
    hybrid_score = (
        config.HYBRID_LEXICAL_WEIGHT * lexical_result.tfidf_score
        + config.HYBRID_SEMANTIC_WEIGHT * semantic_result.semantic_score
    )
    hybrid_score = round(hybrid_score, 6)

    log.info(
        "Pre-classifier: Hybrid scoring (lex=%.4f, sem=%.4f, hybrid=%.4f)",
        lexical_result.tfidf_score,
        semantic_result.semantic_score,
        hybrid_score,
    )

    # ─── Apply hybrid thresholds ─────────────────────────────────────────────
    if hybrid_score < config.HYBRID_PUBLIC_THRESHOLD:
        # Semantic confirmed public
        log.info("Pre-classifier: SKIP (semantic_confirmed_public, hybrid=%.4f)", hybrid_score)
        return {
            "needs_llm": False,
            "reason": f"Hybrid score below public threshold (hybrid={hybrid_score:.4f} < {config.HYBRID_PUBLIC_THRESHOLD})",
            "decision_path": "semantic_confirmed_public",
            "pre_eci": _build_safe_eci(
                f"Hybrid scoring confirmed public (lex={lexical_result.tfidf_score:.4f}, "
                f"sem={semantic_result.semantic_score:.4f}, hybrid={hybrid_score:.4f})"
            ),
            "knowledge_hits": knowledge_hits,
            "lexical_result": lexical_dict,
            "semantic_result": semantic_dict,
            "hybrid_score": hybrid_score,
        }

    if hybrid_score >= config.HYBRID_ENTERPRISE_THRESHOLD:
        # Semantic confirmed enterprise
        log.info("Pre-classifier: SKIP (semantic_confirmed_enterprise, hybrid=%.4f)", hybrid_score)
        return {
            "needs_llm": False,
            "reason": f"Hybrid score above enterprise threshold (hybrid={hybrid_score:.4f} >= {config.HYBRID_ENTERPRISE_THRESHOLD})",
            "decision_path": "semantic_confirmed_enterprise",
            "pre_eci": _build_enterprise_eci(
                lexical_result, hybrid_score, config.HYBRID_ENTERPRISE_THRESHOLD
            ),
            "knowledge_hits": knowledge_hits,
            "lexical_result": lexical_dict,
            "semantic_result": semantic_dict,
            "hybrid_score": hybrid_score,
        }

    # ─── True ambiguity: LLM needed ─────────────────────────────────────────
    log.info(
        "Pre-classifier: NEEDS LLM (true_ambiguity, hybrid=%.4f in [%.2f, %.2f))",
        hybrid_score,
        config.HYBRID_PUBLIC_THRESHOLD,
        config.HYBRID_ENTERPRISE_THRESHOLD,
    )
    return {
        "needs_llm": True,
        "reason": (
            f"True ambiguity: hybrid score in gray zone "
            f"(hybrid={hybrid_score:.4f}, range=[{config.HYBRID_PUBLIC_THRESHOLD}, {config.HYBRID_ENTERPRISE_THRESHOLD}))"
        ),
        "decision_path": "true_ambiguity",
        "pre_eci": None,
        "knowledge_hits": knowledge_hits,
        "lexical_result": lexical_dict,
        "semantic_result": semantic_dict,
        "hybrid_score": hybrid_score,
    }


# =============================================================================
# Legacy classification (USE_LEGACY_SEARCH=true)
# =============================================================================

def _legacy_classify(
    prompt: str,
    masked_text: str,
    entity_count: int,
    entity_types: set,
) -> dict:
    """
    Original keyword-search-based classification logic.
    Used when config.USE_LEGACY_SEARCH is true.
    """
    knowledge_hits = keyword_search(masked_text, top_k=2, min_score=1)
    top_score = knowledge_hits[0]["score"] if knowledge_hits else 0

    # PATH 3 (legacy): PII detected but NO enterprise keyword overlap
    if entity_count > 0 and top_score < _ENTERPRISE_RELEVANCE_THRESHOLD:
        log.info(
            "Pre-classifier [legacy]: SKIP (PII only, no enterprise context, knowledge_score=%d)",
            top_score,
        )
        return {
            "needs_llm": False,
            "reason": "PII detected but no enterprise-specific context",
            "decision_path": "pii_only",
            "pre_eci": _build_pii_only_eci(entity_types),
            "knowledge_hits": knowledge_hits,
            "lexical_result": None,
            "semantic_result": None,
            "hybrid_score": None,
        }

    # PATH 4 (legacy): No PII, no enterprise keyword overlap
    if entity_count == 0 and top_score < _ENTERPRISE_RELEVANCE_THRESHOLD:
        log.info(
            "Pre-classifier [legacy]: SKIP (no PII, no enterprise context, knowledge_score=%d)",
            top_score,
        )
        return {
            "needs_llm": False,
            "reason": "General knowledge prompt, no enterprise relevance",
            "decision_path": "general_knowledge",
            "pre_eci": _build_safe_eci("No PII, no enterprise keyword overlap"),
            "knowledge_hits": knowledge_hits,
            "lexical_result": None,
            "semantic_result": None,
            "hybrid_score": None,
        }

    # PATH 5 (legacy): Enterprise keyword overlap detected -> LLM NEEDED
    log.info(
        "Pre-classifier [legacy]: NEEDS LLM (enterprise relevance detected, "
        "knowledge_score=%d, entities=%d, top_doc=%s)",
        top_score, entity_count,
        knowledge_hits[0]["filename"] if knowledge_hits else "none",
    )
    return {
        "needs_llm": True,
        "reason": f"Enterprise context detected (knowledge_score={top_score}), LLM classification needed",
        "decision_path": "enterprise_ambiguous",
        "pre_eci": None,
        "knowledge_hits": knowledge_hits,
        "lexical_result": None,
        "semantic_result": None,
        "hybrid_score": None,
    }


# =============================================================================
# Pre-built ECI results for deterministic paths (no LLM needed)
# =============================================================================

def _build_safe_eci(reason: str) -> dict:
    """Confidently safe - no enterprise risk, no compliance impact."""
    return {
        "intent": "Other",
        "documentType": "None",
        "requiresEnterpriseKnowledge": False,
        "containsInternalArchitecture": False,
        "containsImplementationDetails": False,
        "containsSourceCode": False,
        "containsCustomerData": False,
        "containsSecrets": False,
        "impactsGDPR": False,
        "impactsPCIDSS": False,
        "impactsHIPAA": False,
        "impactsISO27001": False,
        "confidence": 1.0,
        "reasoning": [f"Pre-classifier: {reason}"],
    }


def _build_secrets_eci(secret_types: set, all_entity_types: set) -> dict:
    """Secrets detected - mark containsSecrets + relevant compliance flags."""
    has_pii = bool(all_entity_types - _SECRET_ENTITY_TYPES)
    return {
        "intent": "Other",
        "documentType": "Security/Credentials",
        "requiresEnterpriseKnowledge": False,
        "containsInternalArchitecture": False,
        "containsImplementationDetails": False,
        "containsSourceCode": False,
        "containsCustomerData": has_pii,
        "containsSecrets": True,
        "impactsGDPR": has_pii,
        "impactsPCIDSS": False,
        "impactsHIPAA": False,
        "impactsISO27001": True,
        "confidence": 1.0,
        "reasoning": [
            f"Secrets detected by Presidio: {', '.join(sorted(secret_types))}",
            "ISO27001 impacted (credentials in prompt)",
        ],
    }


def _build_pii_only_eci(entity_types: set) -> dict:
    """PII detected but no enterprise context - mark GDPR, skip architecture flags."""
    has_pan = "PAN_NUMBER" in entity_types
    has_personal = bool(entity_types & {
        "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "AADHAAR_NUMBER",
        "PASSPORT_NUMBER", "DRIVING_LICENSE",
    })
    return {
        "intent": "Other",
        "documentType": "Customer Data" if has_personal else "None",
        "requiresEnterpriseKnowledge": False,
        "containsInternalArchitecture": False,
        "containsImplementationDetails": False,
        "containsSourceCode": False,
        "containsCustomerData": has_personal,
        "containsSecrets": False,
        "impactsGDPR": has_personal,
        "impactsPCIDSS": has_pan,
        "impactsHIPAA": False,
        "impactsISO27001": False,
        "confidence": 1.0,
        "reasoning": [
            f"PII detected: {', '.join(sorted(entity_types))}",
            "No enterprise keyword overlap - classified deterministically",
        ],
    }


# Confidence band for deterministic enterprise-detection ECIs: a score right
# at its threshold gets CONFIDENCE_FLOOR (below rules.json's
# eci_min_confidence=0.7 for BLOCK, but above 0.5 for WARN), a score at 1.0
# gets CONFIDENCE_CEILING. This keeps a borderline TF-IDF/hybrid match (e.g.
# driven by a couple of weak/generic matched terms) from auto-BLOCKing with
# the same certainty as a strong, unambiguous match.
_ENTERPRISE_CONFIDENCE_FLOOR = 0.55
_ENTERPRISE_CONFIDENCE_CEILING = 0.95


def _build_enterprise_eci(lexical_result, score: float | None = None, threshold: float | None = None) -> dict:
    """
    Enterprise context detected via lexical/hybrid scoring.

    Args:
        lexical_result: LexicalResult used for reasoning text (top doc, matched terms).
        score: The score that actually triggered this decision (tfidf_score for the
               lexical path, hybrid_score for the hybrid path). Defaults to
               lexical_result.tfidf_score.
        threshold: The threshold `score` cleared to get here. Defaults to
                   config.TFIDF_ENTERPRISE_THRESHOLD.
    """
    if score is None:
        score = lexical_result.tfidf_score
    if threshold is None:
        threshold = config.TFIDF_ENTERPRISE_THRESHOLD

    span = max(1.0 - threshold, 1e-6)
    margin = min(max((score - threshold) / span, 0.0), 1.0)
    confidence = round(
        _ENTERPRISE_CONFIDENCE_FLOOR
        + margin * (_ENTERPRISE_CONFIDENCE_CEILING - _ENTERPRISE_CONFIDENCE_FLOOR),
        4,
    )

    top_doc = lexical_result.top_docs[0]["filename"] if lexical_result.top_docs else "unknown"
    return {
        "intent": "Other",
        "documentType": "Internal Documentation",
        "requiresEnterpriseKnowledge": True,
        "containsInternalArchitecture": True,
        "containsImplementationDetails": True,
        "containsSourceCode": False,
        "containsCustomerData": False,
        "containsSecrets": False,
        "impactsGDPR": False,
        "impactsPCIDSS": False,
        "impactsHIPAA": False,
        "impactsISO27001": True,
        "confidence": confidence,
        "reasoning": [
            f"Enterprise context detected (score={score:.4f}, threshold={threshold:.2f}, "
            f"verdict={lexical_result.verdict})",
            f"Top matching document: {top_doc}",
            f"Matched terms: {', '.join(lexical_result.matched_terms[:10])}",
        ],
    }
