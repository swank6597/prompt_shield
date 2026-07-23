# ollama_client.py
# Thin HTTP client for a locally running Ollama instance serving Phi-3
# Mini. Handles request formatting, timeouts, and basic retry logic.
# This module only sends/receives raw text - parsing and schema
# validation of the response happens in semantic_classifier.py.

import os
import sys
import time
import requests

# config.py lives one level up (backend/), while this file lives in
# backend/ai/. Rather than requiring every caller to have backend/ on
# sys.path, resolve it relative to this file's own location.
_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from config import OLLAMA_HOST, OLLAMA_MODEL, OLLAMA_TIMEOUT_SECONDS, OLLAMA_MAX_RETRIES
from utils.logger import get_logger

log = get_logger("ollama_client")

MODEL_NAME = OLLAMA_MODEL
TIMEOUT_SECONDS = OLLAMA_TIMEOUT_SECONDS
MAX_RETRIES = OLLAMA_MAX_RETRIES


class OllamaError(Exception):
    """Raised when Ollama is unreachable or returns an unusable response."""
    pass


def call_ollama(
    system_prompt: str,
    user_prompt: str,
    timeout: int = TIMEOUT_SECONDS,
    max_retries: int = MAX_RETRIES,
) -> str:
    """
    Sends a system/user prompt pair to Ollama's /api/chat endpoint and
    returns the raw text response (expected to be a JSON string per
    schema.json, but returned as-is here - validation is the caller's job).

    Uses Ollama's "format": "json" option to constrain decoding to valid
    JSON at the model level, in addition to the JSON instructions already
    baked into system_prompt.md - two layers of defense against a small
    model wrapping its answer in extra prose.
    """
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "format": "json",
        "options": {
            # Bounds worst-case generation time - our JSON output rarely
            # needs more than ~300-350 tokens (14 fields, including the 4
            # impactsX compliance flags, + a short reasoning array). Raised
            # from 300 - not because 300 was truncating output (a live
            # smoke-test A/B at 300 vs. 450 produced byte-identical
            # completions either way, proving num_predict wasn't the
            # limiting factor with temperature=0's deterministic decoding),
            # but the larger 14-field schema does need more headroom than
            # the original 10-field budget in the general case, so this
            # stays raised as basic hygiene. See semantic_classifier.py's
            # _fallback_result() docstring for the actual cause of
            # increased fail-closed fallbacks on this schema: phi3:mini
            # occasionally produces a genuinely malformed field (e.g. a
            # corrupted key name, or omitting one required field) -
            # confirmed reproducible/deterministic, not a length issue.
            # Capping generation still matters most on constrained hardware
            # (low-power CPU, limited RAM), where an unusually long/
            # rambling generation is what actually causes timeouts.
            "num_predict": 450,
            # A classifier should give a consistent verdict on the same
            # input. Ollama's default temperature (~0.7-0.8) was causing
            # the same prompt to classify differently across runs.
            "temperature": 0,
            "top_p": 0.1,
        },
    }

    last_error = None
    attempts = max_retries + 1

    for attempt in range(1, attempts + 1):
        log.debug(
            "POST %s/api/chat (model=%s, attempt=%d/%d, system_len=%d, user_len=%d)",
            OLLAMA_HOST, MODEL_NAME, attempt, attempts, len(system_prompt), len(user_prompt),
        )
        try:
            request_start = time.perf_counter()
            response = requests.post(
                f"{OLLAMA_HOST}/api/chat", json=payload, timeout=timeout
            )
            elapsed_ms = (time.perf_counter() - request_start) * 1000
            response.raise_for_status()
            data = response.json()
            content = data["message"]["content"]

            # A small quantized model under CPU load occasionally has its
            # runner stall mid-generation and Ollama returns HTTP 200 with
            # an empty content string rather than an error - raise_for_status()
            # doesn't catch this. Treat it as a retryable failure here rather
            # than handing an empty string back to the caller, who would
            # otherwise only discover the problem one layer up when JSON
            # parsing fails on an empty string.
            if not content or not content.strip():
                raise ValueError("Ollama returned empty message content")

            log.debug("Ollama responded in %.0fms (content_len=%d)", elapsed_ms, len(content))
            return content

        except (requests.RequestException, KeyError, ValueError) as e:
            last_error = e
            if attempt < attempts:
                log.warning(
                    "Ollama call failed (attempt %d/%d): %s - retrying in %ds",
                    attempt, attempts, e, attempt,
                )
                time.sleep(attempt)  # simple linear backoff: 1s, 2s, ...
                continue

    log.error(
        "Ollama call failed after %d attempt(s) (host=%s, model=%s): %s",
        attempts, OLLAMA_HOST, MODEL_NAME, last_error,
    )
    raise OllamaError(
        f"Ollama call failed after {attempts} attempt(s) "
        f"(host={OLLAMA_HOST}, model={MODEL_NAME}): {last_error}"
    )


def warm_up() -> None:
    """
    Sends a trivial request to force Ollama to load the model into
    memory upfront. Call this once before running multiple classify()
    calls in a row (e.g. at the start of a test script) so the load-time
    cost is paid once, not on every individual call.
    """
    try:
        call_ollama("You are a test.", "Say OK.", timeout=TIMEOUT_SECONDS, max_retries=0)
    except OllamaError:
        pass  # caller's subsequent real calls will surface the real error


def is_ollama_available() -> bool:
    """Quick reachability check - useful for a graceful-degradation path
    in semantic_classifier.py if Ollama is down (e.g. during a demo)."""
    try:
        requests.get(f"{OLLAMA_HOST}/api/tags", timeout=3).raise_for_status()
        return True
    except requests.RequestException:
        return False


if __name__ == "__main__":
    # Quick manual check: python ollama_client.py
    # Requires Ollama running locally with `ollama pull phi3:mini` done.
    if not is_ollama_available():
        print(f"Ollama not reachable at {OLLAMA_HOST} - start it with `ollama serve`.")
    else:
        from prompt_builder import build_prompt
        from keyword_search import search

        test_prompt = "Explain our OAuth2 implementation."
        docs = search(test_prompt)
        built = build_prompt(test_prompt, docs)

        print("Calling Ollama...")
        raw_response = call_ollama(built["system"], built["user"])
        print("\n=== RAW RESPONSE ===")
        print(raw_response)