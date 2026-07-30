# providers/ollama_provider.py
# Wraps the existing ollama_client.py into the provider interface expected
# by llm_router.py. This keeps all the existing retry/timeout logic intact
# and just exposes it through a uniform call()/is_available() contract.

import os
import sys

_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
_AI_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
for _d in (_BACKEND_DIR, _AI_DIR):
    if _d not in sys.path:
        sys.path.insert(0, _d)

from ollama_client import call_ollama, is_ollama_available, OllamaError
from utils.logger import get_logger

log = get_logger("provider.ollama")


class OllamaProvider:
    """Local Ollama LLM provider - uses the existing ollama_client.py."""

    name = "local"

    def call(self, system_prompt: str, user_prompt: str) -> str:
        """
        Send a system/user prompt pair to local Ollama and return the raw
        text response. Raises OllamaError on failure (handled by router).
        """
        log.debug("OllamaProvider.call() - sending to local Ollama")
        return call_ollama(system_prompt, user_prompt)

    def is_available(self) -> bool:
        """Quick reachability check for Ollama."""
        return is_ollama_available()
