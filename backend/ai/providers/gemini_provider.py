# providers/gemini_provider.py
# Google Gemini LLM provider - uses the new `google-genai` SDK (successor
# to the deprecated `google-generativeai` package).
#
# Free tier: 15 requests/minute, 1 million tokens/day
# Get your API key: https://aistudio.google.com/apikey
#
# Set it in backend/.env:
#   PROMPTSHIELD_GEMINI_API_KEY=your_key_here

import os
import sys

_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
_AI_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
for _d in (_BACKEND_DIR, _AI_DIR):
    if _d not in sys.path:
        sys.path.insert(0, _d)

from config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_TIMEOUT_SECONDS
from utils.logger import get_logger

log = get_logger("provider.gemini")


class GeminiProviderError(Exception):
    """Raised when the Gemini API call fails."""
    pass


class GeminiProvider:
    """Cloud LLM provider using Google's Gemini API via the google-genai SDK."""

    # Registry name - used by the dynamic provider registry in llm_router.py
    name = "gemini"

    def __init__(self):
        self._api_key = GEMINI_API_KEY
        self._model_name = GEMINI_MODEL
        self._timeout = GEMINI_TIMEOUT_SECONDS
        self._client = None

    def _get_client(self):
        """Lazy-initialize the google-genai Client."""
        if self._client is None:
            if not self._api_key:
                raise GeminiProviderError(
                    "PROMPTSHIELD_GEMINI_API_KEY not set. "
                    "Get a free key at https://aistudio.google.com/apikey"
                )

            try:
                from google import genai
            except ImportError:
                raise GeminiProviderError(
                    "google-genai package not installed. "
                    "Run: pip install google-genai"
                )

            self._client = genai.Client(api_key=self._api_key)

        return self._client

    def call(self, system_prompt: str, user_prompt: str) -> str:
        """
        Send a system/user prompt pair to Google Gemini and return the
        raw text response.

        Uses the google-genai SDK's generate_content with:
          - system_instruction for the system prompt
          - response_mime_type="application/json" for constrained JSON output
          - temperature=0 for deterministic classification
        """
        log.debug(
            "GeminiProvider.call() - model=%s, system_len=%d, user_len=%d",
            self._model_name, len(system_prompt), len(user_prompt),
        )

        if not self._api_key:
            raise GeminiProviderError(
                "PROMPTSHIELD_GEMINI_API_KEY not set. "
                "Get a free key at https://aistudio.google.com/apikey"
            )

        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise GeminiProviderError(
                "google-genai package not installed. "
                "Run: pip install google-genai"
            )

        try:
            client = self._get_client()

            response = client.models.generate_content(
                model=self._model_name,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0,
                    top_p=0.1,
                    max_output_tokens=1024,
                    response_mime_type="application/json",
                ),
            )

            # Extract text from response
            if not response.candidates:
                raise GeminiProviderError("Gemini returned no candidates")

            content = response.text
            if not content or not content.strip():
                raise GeminiProviderError("Gemini returned empty response content")

            log.debug("Gemini responded (content_len=%d)", len(content))
            return content

        except GeminiProviderError:
            raise
        except Exception as e:
            raise GeminiProviderError(f"Gemini API call failed: {e}") from e

    def is_available(self) -> bool:
        """Check if Gemini is configured (API key present + SDK installed)."""
        if not self._api_key:
            return False
        try:
            from google import genai  # noqa: F401
            return True
        except ImportError:
            return False
