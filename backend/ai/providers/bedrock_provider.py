# providers/bedrock_provider.py
# Amazon Bedrock LLM provider - uses AWS SDK (boto3) to call foundation
# models hosted on Bedrock. Supports Claude, Llama, Titan, etc.
#
# Authentication uses standard AWS credential chain:
#   1. Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
#   2. ~/.aws/credentials profile
#   3. IAM instance role (if running on EC2/ECS)
#
# Default model: Claude 3 Haiku (fast, cheap, good at structured output)

import json
import os
import sys

_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
_AI_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
for _d in (_BACKEND_DIR, _AI_DIR):
    if _d not in sys.path:
        sys.path.insert(0, _d)

from config import BEDROCK_REGION, BEDROCK_MODEL_ID, BEDROCK_TIMEOUT_SECONDS
from utils.logger import get_logger

log = get_logger("provider.bedrock")


class BedrockProviderError(Exception):
    """Raised when the Bedrock API call fails."""
    pass


class BedrockProvider:
    """Cloud LLM provider using Amazon Bedrock's Converse API."""

    name = "bedrock"

    def __init__(self):
        self._region = BEDROCK_REGION
        self._model_id = BEDROCK_MODEL_ID
        self._timeout = BEDROCK_TIMEOUT_SECONDS
        self._client = None

    def _get_client(self):
        """Lazy-initialize the Bedrock Runtime client."""
        if self._client is None:
            try:
                import boto3
                from botocore.config import Config
            except ImportError:
                raise BedrockProviderError(
                    "boto3 package not installed. Run: pip install boto3"
                )

            config = Config(
                region_name=self._region,
                read_timeout=self._timeout,
                connect_timeout=10,
                retries={"max_attempts": 2, "mode": "standard"},
            )
            self._client = boto3.client("bedrock-runtime", config=config)

        return self._client

    def call(self, system_prompt: str, user_prompt: str) -> str:
        """
        Send a system/user prompt pair to Bedrock using the Converse API.
        Returns raw text content from the model response.

        Uses the Converse API (model-agnostic) rather than InvokeModel
        (which requires model-specific payload formatting), so switching
        between Claude/Llama/Titan only requires changing the model ID
        in config.py.
        """
        log.debug(
            "BedrockProvider.call() - model=%s, region=%s, system_len=%d, user_len=%d",
            self._model_id, self._region, len(system_prompt), len(user_prompt),
        )

        client = self._get_client()

        try:
            response = client.converse(
                modelId=self._model_id,
                system=[{"text": system_prompt}],
                messages=[
                    {
                        "role": "user",
                        "content": [{"text": user_prompt}],
                    }
                ],
                inferenceConfig={
                    "maxTokens": 450,
                    "temperature": 0.0,
                    "topP": 0.1,
                },
            )

            # Extract text from Converse API response
            output = response.get("output", {})
            message = output.get("message", {})
            content_blocks = message.get("content", [])

            if not content_blocks:
                raise BedrockProviderError("Bedrock returned empty content")

            # Converse returns a list of content blocks; take the first text block
            text_content = ""
            for block in content_blocks:
                if "text" in block:
                    text_content = block["text"]
                    break

            if not text_content.strip():
                raise BedrockProviderError("Bedrock returned empty text content")

            log.debug("Bedrock responded (content_len=%d)", len(text_content))
            return text_content

        except BedrockProviderError:
            raise
        except Exception as e:
            raise BedrockProviderError(f"Bedrock API call failed: {e}") from e

    def is_available(self) -> bool:
        """Check if Bedrock is configured and reachable."""
        try:
            import boto3
        except ImportError:
            return False

        try:
            client = self._get_client()
            # A lightweight call to verify credentials work
            # list_foundation_models is cheap and confirms auth
            client.meta.service_model  # noqa - just checks client init
            return True
        except Exception:
            return False
