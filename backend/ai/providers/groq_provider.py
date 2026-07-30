# providers/groq_provider.py
# Groq cloud LLM provider - uses the Groq API (free tier available) for
# fast inference on open-source models like Llama 3.1 8B Instant.
#
# Groq's free tier gives 30 requests/min on smaller models which is more
# than enough for a hackathon demo scanning individual prompts.
#
# Get a free API key: https://console.groq.com/keys
# Set it: $env:PROMPTSHIELD_GROQ_API_KEY = "gsk_..."

import os
import sys

_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
_AI_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
for _d in (_BACKEND_DIR, _AI_DIR):
    if _d not in sys.path:
        sys.path.insert(0, _d)

from config import GROQ_API_KEY, GROQ_MODEL, GROQ_TIMEOUT_SECONDS
from utils.logger import get_logger

log = get_logger("provider.groq")


class GroqProviderError(Exception):
    """Raised when the Groq API call fails."""
    pass


class GroqProvider:
    """Cloud LLM provider using Groq's fast inference API."""

    name = "groq"

    def __init__(self):
        self._api_key = GROQ_API_KEY
        self._model = GROQ_MODEL
        self._timeout = GROQ_TIMEOUT_SECONDS

    def call(self, system_prompt: str, user_prompt: str) -> str:
        """
        Send a system/user prompt pair to Groq's chat completions API.
        Returns raw text content from the model response.
        """
        if not self._api_key:
            raise GroqProviderError(
                "PROMPTSHIELD_GROQ_API_KEY not set. "
                "Get a free key at https://console.groq.com/keys"
            )

        # Import here to avoid hard dependency if groq isn't installed
        # and this provider is never used.
        try:
            from groq import Groq
        except ImportError:
            raise GroqProviderError(
                "groq package not installed. Run: pip install groq"
            )

        log.debug(
            "GroqProvider.call() - model=%s, system_len=%d, user_len=%d",
            self._model, len(system_prompt), len(user_prompt),
        )

        try:
            client = Groq(api_key=self._api_key, timeout=self._timeout)
            response = client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
                top_p=0.1,
                max_tokens=450,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            if not content or not content.strip():
                raise GroqProviderError("Groq returned empty response content")

            log.debug("Groq responded (content_len=%d)", len(content))
            return content

        except GroqProviderError:
            raise
        except Exception as e:
            raise GroqProviderError(f"Groq API call failed: {e}") from e

    def is_available(self) -> bool:
        """Check if Groq is configured (API key present)."""
        if not self._api_key:
            return False
        # Optionally verify connectivity - for now just check config
        try:
            from groq import Groq
            return True
        except ImportError:
            return False
