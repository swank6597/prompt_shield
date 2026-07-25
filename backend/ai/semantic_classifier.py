# semantic_classifier.py
# Enterprise Context Intelligence (ECI) analyzer - orchestrates
# keyword_search -> prompt_builder -> LLM Router, then parses/validates
# the LLM's JSON response against schema.json and returns the structured
# ECIClassificationResult.
#
# This classifier only understands context; it does not decide
# Allow/Warn/Mask/Block - that is policy_engine.py's job, using this
# module's output as one of its inputs.
#
# Fail-closed by design: if all LLM providers are unreachable, or the
# model's output doesn't parse/validate even after one retry, this returns
# a cautious default (requiresEnterpriseKnowledge=True, confidence=0.0)
# rather than silently letting an unclassified prompt through as "safe".
# classify() never raises - callers can rely on always getting a
# schema-shaped dict.

import json
import os
import sys

from jsonschema import validate, ValidationError

from keyword_search import search
from prompt_builder import build_prompt
from llm_router import route_llm_call, is_any_provider_available, LLMRouterError

# backend/ lives one level up - needed for utils.logger and config.
_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from utils.logger import get_logger  # noqa: E402

log = get_logger("semantic_classifier")

_DIR = os.path.dirname(__file__)
SCHEMA_PATH = os.path.join(_DIR, "schema.json")

with open(SCHEMA_PATH, "r", encoding="utf-8") as _f:
    _SCHEMA = json.load(_f)

MAX_PARSE_RETRIES = 1  # one retry on top of the first attempt, same prompt


def _fallback_result(reason: str) -> dict:
    """
    Fail-closed default. Used when Ollama is down or its output can't be
    trusted. requiresEnterpriseKnowledge=True + confidence=0.0 signals
    "could not classify - treat with caution" to the Policy Engine,
    rather than defaulting to a false "this looks fine".

    Known limitation (confirmed via live smoke test after the 4 impactsX
    compliance fields were added, growing the schema from 10 to 14
    required fields): phi3:mini's structured-output reliability degrades
    somewhat at this schema size - it occasionally emits a malformed
    field (a corrupted key name, or omits one required field) and this
    path gets hit more often than before as a result. Confirmed this is
    NOT a token-budget/truncation issue (a live A/B at num_predict 300 vs.
    450 produced byte-identical completions - see ollama_client.py) but a
    genuine, reproducible small-model generation limitation on a schema
    this size. This is a real accuracy/latency trade-off worth revisiting
    (e.g. a larger/instruction-tuned model, or splitting compliance
    mapping into its own lighter schema) but is not unsafe: every failure
    here still correctly resolves to this fail-closed WARN path rather
    than silently passing bad data through.
    """
    return {
        "intent": "Other",
        "documentType": "None",
        "requiresEnterpriseKnowledge": True,
        "containsInternalArchitecture": False,
        "containsImplementationDetails": False,
        "containsSourceCode": False,
        "containsCustomerData": False,
        "containsSecrets": False,
        "impactsGDPR": False,
        "impactsPCIDSS": False,
        "impactsHIPAA": False,
        "impactsISO27001": False,
        "confidence": 0.0,
        "reasoning": [f"ECI fallback triggered: {reason}"],
    }


def skipped_result(reason: str) -> dict:
    """
    Router-skip default: confidently benign, NOT fail-closed. Used by
    routes.py when the Smart Analysis Router decided a prompt is trivial
    (and Presidio found nothing) and chose not to call Ollama at all.

    Deliberately the OPPOSITE posture from _fallback_result(): that one
    is confidence=0.0 to signal "we tried and couldn't classify, be
    cautious" (which rules.json's warn_eci_could_not_classify rule turns
    into WARN). Reusing it here would mean every skipped trivial prompt
    incorrectly comes back WARN instead of ALLOW. confidence=1.0 + all
    flags False keeps the decision on ALLOW, matching what would happen
    if Ollama had actually run and found nothing.
    """
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
        "reasoning": [f"Skipped by Smart Analysis Router: {reason}"],
    }


def _parse_and_validate(raw_text: str) -> dict:
    parsed = json.loads(raw_text)          # raises json.JSONDecodeError
    validate(instance=parsed, schema=_SCHEMA)  # raises jsonschema.ValidationError
    return parsed


def classify(masked_text: str, entity_count: int = 0) -> dict:
    """
    Runs the full ECI pipeline on already-masked text (output of the
    Regex + Presidio layers) and returns a dict matching schema.json.

    Args:
        masked_text: The prompt after Presidio masking.
        entity_count: Number of entities Presidio detected (passed to the
                      router for auto-strategy complexity scoring).

    Never raises - any failure path returns _fallback_result(...) so
    routes.py / policy_engine.py don't need their own try/except around
    this call.
    """
    if not is_any_provider_available():
        log.warning("No LLM provider available - returning fail-closed fallback")
        return _fallback_result("No LLM provider reachable")

    retrieved_docs = search(masked_text)
    if retrieved_docs:
        log.debug(
            "Retrieved %d knowledge doc(s): %s",
            len(retrieved_docs), [d["filename"] for d in retrieved_docs],
        )
    built = build_prompt(masked_text, retrieved_docs)

    # Context passed to the router for smart auto-routing decisions
    router_context = {
        "prompt_text": masked_text,
        "entity_count": entity_count,
    }

    last_error = None
    for attempt in range(MAX_PARSE_RETRIES + 1):
        try:
            raw = route_llm_call(built["system"], built["user"], context=router_context)
        except LLMRouterError as e:
            log.error("LLM Router failed: %s - returning fail-closed fallback", e)
            return _fallback_result(f"LLM Router failed: {e}")

        # Log raw LLM output at DEBUG level so we can diagnose parse failures
        log.debug("Raw LLM response (attempt %d, len=%d):\n%s", attempt + 1, len(raw), raw)

        try:
            parsed = _parse_and_validate(raw)
            log.debug("ECI classification parsed and validated on attempt %d", attempt + 1)
            return parsed
        except (json.JSONDecodeError, ValidationError) as e:
            last_error = e
            log.warning("ECI output failed validation on attempt %d: %s\nRaw output was: %s", attempt + 1, e, raw[:500])
            continue  # retry once with the same prompt

    log.error("ECI output failed validation after all retries: %s - returning fail-closed fallback", last_error)
    return _fallback_result(f"LLM output failed validation after retries: {last_error}")


if __name__ == "__main__":
    # Quick manual check: python semantic_classifier.py
    # Full live run needs at least one LLM provider available:
    #   - Local: Ollama running with phi3:mini pulled
    #   - Cloud: PROMPTSHIELD_GROQ_API_KEY set, or AWS credentials configured
    # If nothing is available, this demonstrates the fail-closed fallback path.
    test_prompts = [
        "Explain OAuth2.",
        "Explain our OAuth2 implementation.",
        "Why does the Mercury payment flow retry before failing over?",
    ]
    for p in test_prompts:
        print(f"\nPrompt: {p!r}")
        result = classify(p)
        print(json.dumps(result, indent=2))