# pre_classifier.py
# Deterministic pre-classifier that decides whether an LLM call is needed.
#
# The goal: AVOID expensive LLM calls when cheaper signals already give
# a definitive answer. This saves tokens, money, and 10-20s of latency.
#
# Decision matrix:
#
#   Presidio found secrets/credentials?
#     YES -> policy will BLOCK anyway, LLM adds nothing -> SKIP (hard_block)
#
#   Presidio found PII but no secrets?
#     YES + no enterprise keyword overlap -> SKIP (pii_only, policy will MASK)
#     YES + enterprise keyword overlap -> NEEDS LLM (gray zone)
#
#   Presidio found nothing?
#     Trivial prompt (greetings, single words)? -> SKIP (trivial)
#     No keyword overlap with knowledge base? -> SKIP (general_knowledge)
#     Has keyword overlap (enterprise terms detected)? -> NEEDS LLM
#
# The key insight: the LLM is ONLY needed when the prompt might be leaking
# enterprise-specific context that Presidio can't catch (no PII, but uses
# internal terminology). That's the gray zone where a human-like judgment
# call is required.

import os
import sys

_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_AI_DIR = os.path.dirname(__file__)
for _d in (_BACKEND_DIR, _AI_DIR):
    if _d not in sys.path:
        sys.path.insert(0, _d)

from keyword_search import search as keyword_search
from utils.helpers import is_trivial_prompt
from utils.logger import get_logger

log = get_logger("pre_classifier")

# Entity types that indicate secrets/credentials - if Presidio catches these,
# the policy engine will BLOCK regardless of what the LLM says.
_SECRET_ENTITY_TYPES = {
    "GITHUB_TOKEN", "OPENAI_API_KEY", "AWS_ACCESS_KEY",
    "AWS_SECRET_KEY", "PRIVATE_KEY", "JWT_TOKEN",
}

# Minimum keyword search score to consider a prompt "enterprise-relevant"
# enough to warrant an LLM call. Below this, the prompt has minimal overlap
# with enterprise knowledge and can be classified deterministically.
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
            "needs_llm": bool,        # True = must call LLM, False = skip it
            "reason": str,            # Human-readable explanation
            "decision_path": str,     # Machine-readable path taken
            "pre_eci": dict | None,   # Pre-filled ECI result if LLM skipped
            "knowledge_hits": list,   # Top keyword search matches (for reuse)
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
        }

    # =========================================================================
    # PATH 2: Secrets detected -> policy will BLOCK, LLM adds nothing
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
        }

    # =========================================================================
    # Check enterprise knowledge relevance (keyword search)
    # =========================================================================
    knowledge_hits = keyword_search(masked_text, top_k=2, min_score=1)
    top_score = knowledge_hits[0]["score"] if knowledge_hits else 0

    # =========================================================================
    # PATH 3: PII detected but NO enterprise keyword overlap -> just PII leak
    # =========================================================================
    if entity_count > 0 and top_score < _ENTERPRISE_RELEVANCE_THRESHOLD:
        log.info(
            "Pre-classifier: SKIP (PII only, no enterprise context, knowledge_score=%d)",
            top_score,
        )
        return {
            "needs_llm": False,
            "reason": "PII detected but no enterprise-specific context",
            "decision_path": "pii_only",
            "pre_eci": _build_pii_only_eci(entity_types),
            "knowledge_hits": knowledge_hits,
        }

    # =========================================================================
    # PATH 4: No PII, no enterprise keyword overlap -> general knowledge
    # =========================================================================
    if entity_count == 0 and top_score < _ENTERPRISE_RELEVANCE_THRESHOLD:
        log.info(
            "Pre-classifier: SKIP (no PII, no enterprise context, knowledge_score=%d)",
            top_score,
        )
        return {
            "needs_llm": False,
            "reason": "General knowledge prompt, no enterprise relevance",
            "decision_path": "general_knowledge",
            "pre_eci": _build_safe_eci("No PII, no enterprise keyword overlap"),
            "knowledge_hits": knowledge_hits,
        }

    # =========================================================================
    # PATH 5: Enterprise keyword overlap detected -> LLM NEEDED
    # This is the gray zone: prompt uses enterprise terminology but may or
    # may not actually be leaking internal info. Only the LLM can judge.
    # =========================================================================
    log.info(
        "Pre-classifier: NEEDS LLM (enterprise relevance detected, "
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
    # Simple heuristic: if PAN detected, mark PCI-DSS
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
