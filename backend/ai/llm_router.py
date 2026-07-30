# llm_router.py
# Smart LLM Router - decides which provider handles each classification
# request based on developer-configured strategy and runtime heuristics.
#
# Routing strategies:
#   "local"  -> Always use local Ollama (original behavior, no network needed)
#   "cloud"  -> Always use the configured cloud provider (Groq, Bedrock, Gemini)
#   "auto"   -> Pick provider per-request based on prompt length, entity
#               count from Presidio, and keyword complexity signals
#
# The router is the ONLY module that semantic_classifier.py calls for LLM
# inference. It abstracts away which backend actually runs the model.
#
# ADDING A NEW PROVIDER:
#   1. Create providers/my_provider.py with name, call(), is_available()
#   2. Import it in providers/__init__.py and add to PROVIDER_CLASSES
#   3. Add config vars to config.py + .env.example
#   The router picks it up automatically from PROVIDER_REGISTRY.
#
# Usage:
#   from llm_router import route_llm_call
#   response_text, provider_used = route_llm_call(system_prompt, user_prompt, context={...})

import os
import re
import sys

_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from config import (
    LLM_STRATEGY,
    LLM_CLOUD_PROVIDER,
    LLM_AUTO_LENGTH_THRESHOLD,
    LLM_AUTO_ENTITY_THRESHOLD,
    LLM_FALLBACK_TO_LOCAL,
    OLLAMA_MODEL,
    GROQ_MODEL,
    GEMINI_MODEL,
    BEDROCK_MODEL_ID,
)
from utils.logger import get_logger

# Dynamic provider registry - no hardcoded provider imports here.
# Adding a new provider only requires editing providers/__init__.py.
from providers import PROVIDER_REGISTRY

log = get_logger("llm_router")

# Resolves a provider name to the actual model string it's configured to
# use - lets callers (semantic_classifier.py, for the audit trail) report
# which model served a request without duplicating config knowledge.
PROVIDER_MODEL = {
    "local": OLLAMA_MODEL,
    "groq": GROQ_MODEL,
    "gemini": GEMINI_MODEL,
    "bedrock": BEDROCK_MODEL_ID,
}

# ---------------------------------------------------------------------------
# Provider instances (lazy-initialized singletons)
# ---------------------------------------------------------------------------
_provider_instances: dict = {}


def _get_provider(name: str):
    """Get or create a singleton provider instance by name."""
    if name not in _provider_instances:
        cls = PROVIDER_REGISTRY.get(name)
        if cls is None:
            available = list(PROVIDER_REGISTRY.keys())
            raise ValueError(
                f"Unknown LLM provider: {name!r}. "
                f"Available providers: {available}. "
                f"To add a new provider, see providers/__init__.py."
            )
        _provider_instances[name] = cls()
        log.info("Initialized LLM provider: %s", name)
    return _provider_instances[name]


def get_available_providers() -> list[str]:
    """Return a list of all registered provider names."""
    return list(PROVIDER_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Complexity heuristics for "auto" strategy
# ---------------------------------------------------------------------------
# Keywords that suggest the prompt involves enterprise/sensitive context
# and benefits from a more capable (cloud) model.
_COMPLEXITY_KEYWORDS = re.compile(
    r"\b(architecture|implementation|infrastructure|deployment|pipeline|"
    r"oauth|authentication|authorization|encryption|certificate|"
    r"database|schema|migration|microservice|kubernetes|terraform|"
    r"compliance|gdpr|pci|hipaa|iso\s*27001|audit|"
    r"source\s*code|api\s*key|secret|credential|token|password)\b",
    re.IGNORECASE,
)


def _compute_complexity_score(prompt_text: str, entity_count: int = 0) -> dict:
    """
    Returns a dict with routing decision metadata:
      - word_count: number of words in the prompt
      - keyword_hits: number of complexity keyword matches
      - entity_count: PII entities found by Presidio
      - route_to_cloud: bool - whether heuristics suggest cloud is better
      - reason: human-readable explanation of the routing decision
    """
    words = prompt_text.split()
    word_count = len(words)
    keyword_hits = len(_COMPLEXITY_KEYWORDS.findall(prompt_text))

    # Decision logic:
    # 1. If prompt is long (> threshold words), cloud handles it faster
    # 2. If many entities detected, classification is complex -> cloud
    # 3. If complexity keywords present (>= 2 hits), cloud model is more reliable
    reasons = []

    if word_count > LLM_AUTO_LENGTH_THRESHOLD:
        reasons.append(f"prompt length ({word_count} words) exceeds threshold ({LLM_AUTO_LENGTH_THRESHOLD})")

    if entity_count > LLM_AUTO_ENTITY_THRESHOLD:
        reasons.append(f"entity count ({entity_count}) exceeds threshold ({LLM_AUTO_ENTITY_THRESHOLD})")

    if keyword_hits >= 2:
        reasons.append(f"complexity keywords detected ({keyword_hits} hits)")

    route_to_cloud = len(reasons) > 0

    return {
        "word_count": word_count,
        "keyword_hits": keyword_hits,
        "entity_count": entity_count,
        "route_to_cloud": route_to_cloud,
        "reason": "; ".join(reasons) if reasons else "prompt is short and simple -> local",
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_provider_name(strategy: str = LLM_STRATEGY, cloud_provider: str = LLM_CLOUD_PROVIDER,
                          prompt_text: str = "", entity_count: int = 0) -> tuple[str, str]:
    """
    Determines which provider to use based on strategy and context.
    Returns (provider_name, reason).
    """
    if strategy == "local":
        return "local", "strategy=local (developer override)"

    if strategy == "cloud":
        return cloud_provider, f"strategy=cloud (developer override -> {cloud_provider})"

    if strategy == "auto":
        score = _compute_complexity_score(prompt_text, entity_count)
        if score["route_to_cloud"]:
            return cloud_provider, f"strategy=auto routed to {cloud_provider}: {score['reason']}"
        else:
            return "local", f"strategy=auto routed to local: {score['reason']}"

    # Unknown strategy - default to local with a warning
    log.warning("Unknown LLM_STRATEGY=%r, defaulting to local", strategy)
    return "local", f"unknown strategy {strategy!r}, defaulting to local"


def route_llm_call(
    system_prompt: str,
    user_prompt: str,
    context: dict | None = None,
) -> tuple[str, str]:
    """
    Routes an LLM classification call to the appropriate provider.

    Args:
        system_prompt: The system prompt (role/instructions).
        user_prompt: The user/classifier prompt (the actual request).
        context: Optional dict with routing hints:
            - "prompt_text": original prompt text (for complexity analysis)
            - "entity_count": number of Presidio entities detected
            - "force_provider": override to force a specific provider name
                               (must match a name in PROVIDER_REGISTRY)

    Returns:
        (response_text, provider_used) - response_text is the raw text
        response from the LLM (expected to be JSON per schema.json);
        provider_used is whichever provider actually served the request -
        this can differ from the initially-resolved provider if it failed
        and fell back to local, so callers needing an audit trail should
        use this value, not resolve_provider_name()'s independently.

    Raises:
        LLMRouterError: if all providers fail (including fallback).
    """
    context = context or {}
    prompt_text = context.get("prompt_text", user_prompt)
    entity_count = context.get("entity_count", 0)
    force_provider = context.get("force_provider")

    # Developer can force a specific provider per-call via context
    if force_provider:
        provider_name = force_provider
        reason = f"forced by caller: {force_provider}"
    else:
        provider_name, reason = resolve_provider_name(
            prompt_text=prompt_text,
            entity_count=entity_count,
        )

    log.info("LLM Router: %s (provider=%s)", reason, provider_name)

    # Attempt primary provider
    provider = _get_provider(provider_name)
    try:
        return provider.call(system_prompt, user_prompt), provider_name
    except Exception as primary_error:
        log.error("Primary provider %s failed: %s", provider_name, primary_error)

        # Fallback logic: if cloud failed and fallback is enabled, try local
        if provider_name != "local" and LLM_FALLBACK_TO_LOCAL:
            log.info("Falling back to local Ollama...")
            try:
                fallback = _get_provider("local")
                return fallback.call(system_prompt, user_prompt), "local"
            except Exception as fallback_error:
                log.error("Fallback to local also failed: %s", fallback_error)
                raise LLMRouterError(
                    f"All providers failed. Primary ({provider_name}): {primary_error}; "
                    f"Fallback (local): {fallback_error}"
                ) from fallback_error

        raise LLMRouterError(
            f"Provider {provider_name} failed and fallback is disabled: {primary_error}"
        ) from primary_error


def is_any_provider_available() -> bool:
    """
    Quick check: is at least one configured provider reachable?
    Used by semantic_classifier.py's fail-closed path.
    """
    strategy = LLM_STRATEGY

    if strategy == "local":
        provider = _get_provider("local")
        return provider.is_available()

    if strategy == "cloud":
        provider = _get_provider(LLM_CLOUD_PROVIDER)
        if provider.is_available():
            return True
        if LLM_FALLBACK_TO_LOCAL:
            return _get_provider("local").is_available()
        return False

    # "auto" - either local or cloud must be up
    local_ok = _get_provider("local").is_available()
    cloud_ok = _get_provider(LLM_CLOUD_PROVIDER).is_available()
    return local_ok or cloud_ok


class LLMRouterError(Exception):
    """Raised when all configured LLM providers fail."""
    pass
