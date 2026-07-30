# providers/__init__.py
# Dynamic LLM provider registry for the Smart Router.
#
# Each provider class exposes a uniform interface:
#   .name              -> str (registry key, e.g. "groq", "gemini", "local")
#   .call(system, user) -> str (raw LLM text response)
#   .is_available()    -> bool (quick health/config check)
#
# TO ADD A NEW PROVIDER:
#   1. Create a new file in this folder: providers/my_provider.py
#   2. Define a class with `name`, `call()`, and `is_available()`
#   3. Import it below and add it to PROVIDER_CLASSES
#   4. Add its config vars to config.py and .env.example
#   That's it — the router picks it up automatically.

from providers.ollama_provider import OllamaProvider
from providers.groq_provider import GroqProvider
from providers.bedrock_provider import BedrockProvider
from providers.gemini_provider import GeminiProvider

# Master list of all available provider classes.
# The router builds its registry from this list using each class's .name attribute.
PROVIDER_CLASSES = [
    OllamaProvider,
    GroqProvider,
    BedrockProvider,
    GeminiProvider,
]

# Convenience dict: provider_name -> class (built dynamically)
PROVIDER_REGISTRY = {cls.name: cls for cls in PROVIDER_CLASSES}

__all__ = [
    "OllamaProvider",
    "GroqProvider",
    "BedrockProvider",
    "GeminiProvider",
    "PROVIDER_CLASSES",
    "PROVIDER_REGISTRY",
]
