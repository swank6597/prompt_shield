# semantic_classifier.py
# Enterprise Context Intelligence (ECI) analyzer - orchestrates
# keyword_search -> prompt_builder -> ollama_client, then parses/validates
# the LLM's JSON response against schema.json and returns the structured
# ECIClassificationResult.
#
# This classifier only understands context; it does not decide
# Allow/Warn/Mask/Block - that is policy_engine.py's job, using this
# module's output as one of its inputs.
#
# Fail-closed by design: if Ollama is unreachable, or the model's output
# doesn't parse/validate even after one retry, this returns a cautious
# default (requiresEnterpriseKnowledge=True, confidence=0.0) rather than
# silently letting an unclassified prompt through as "safe". classify()
# never raises - callers can rely on always getting a schema-shaped dict.

import json
import os
import sys

from jsonschema import validate, ValidationError

from keyword_search import search
from prompt_builder import build_prompt
from ollama_client import call_ollama, is_ollama_available, OllamaError

# backend/ lives one level up - needed for utils.logger. ollama_client.py
# (imported above) already inserts it into sys.path as a side effect, but
# don't rely on import order: insert it here too so this module works
# standalone regardless of what else has already run.
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
        "confidence": 0.0,
        "reasoning": [f"ECI fallback triggered: {reason}"],
    }


def _parse_and_validate(raw_text: str) -> dict:
    parsed = json.loads(raw_text)          # raises json.JSONDecodeError
    validate(instance=parsed, schema=_SCHEMA)  # raises jsonschema.ValidationError
    return parsed


def classify(masked_text: str) -> dict:
    """
    Runs the full ECI pipeline on already-masked text (output of the
    Regex + Presidio layers) and returns a dict matching schema.json.

    Never raises - any failure path returns _fallback_result(...) so
    routes.py / policy_engine.py don't need their own try/except around
    this call.
    """
    if not is_ollama_available():
        log.warning("Ollama unreachable - returning fail-closed fallback")
        return _fallback_result("Ollama unreachable")

    retrieved_docs = search(masked_text)
    if retrieved_docs:
        log.debug(
            "Retrieved %d knowledge doc(s): %s",
            len(retrieved_docs), [d["filename"] for d in retrieved_docs],
        )
    built = build_prompt(masked_text, retrieved_docs)

    last_error = None
    for attempt in range(MAX_PARSE_RETRIES + 1):
        try:
            raw = call_ollama(built["system"], built["user"])
        except OllamaError as e:
            log.error("Ollama call failed: %s - returning fail-closed fallback", e)
            return _fallback_result(f"Ollama call failed: {e}")

        try:
            parsed = _parse_and_validate(raw)
            log.debug("ECI classification parsed and validated on attempt %d", attempt + 1)
            return parsed
        except (json.JSONDecodeError, ValidationError) as e:
            last_error = e
            log.warning("ECI output failed validation on attempt %d: %s", attempt + 1, e)
            continue  # retry once with the same prompt

    log.error("ECI output failed validation after all retries: %s - returning fail-closed fallback", last_error)
    return _fallback_result(f"LLM output failed validation after retries: {last_error}")


if __name__ == "__main__":
    # Quick manual check: python semantic_classifier.py
    # Full live run needs Ollama running with phi3:mini pulled - if not
    # available, this will demonstrate the fail-closed fallback path
    # instead, which is itself a useful thing to confirm works.
    test_prompts = [
        "Explain OAuth2.",
        "Explain our OAuth2 implementation.",
        "Why does the Mercury payment flow retry before failing over?",
    ]
    for p in test_prompts:
        print(f"\nPrompt: {p!r}")
        result = classify(p)
        print(json.dumps(result, indent=2))