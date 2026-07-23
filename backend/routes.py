# routes.py
# API route definitions. Currently exposes the Presidio-only /analyze
# endpoint (merged from the POC's api.py) plus /health. /api/scan now also
# runs the ECI (ai/) layer on Presidio's masked text. Regex and the Policy
# Engine still need to be wired in - once they are, this becomes the full
# orchestration point: Regex -> Presidio -> ECI -> Policy Engine.

import os
import sys

from fastapi import APIRouter

from models import AnalyzeRequest, AnalyzeResponse, ECIResult, EntityResult, ScanRequest, ScanResponse
from presidio.presidio_engine import analyze_text

# backend/ai/'s modules use bare imports (e.g. `from keyword_search import
# search`) that assume backend/ai is on sys.path, the same pattern
# ollama_client.py already uses for backend/ itself. Mirrored here rather
# than refactored so the ai/ modules keep working when run standalone
# (`python backend/ai/semantic_classifier.py`, tests/test_eci_smoke.py).
_AI_DIR = os.path.join(os.path.dirname(__file__), "ai")
if _AI_DIR not in sys.path:
    sys.path.insert(0, _AI_DIR)

from semantic_classifier import classify as classify_context  # noqa: E402

router = APIRouter()


@router.get("/health")
def health():
    return {
        "status": "UP",
        "service": "PromptShield Detection API",
        "version": "1.0.0",
    }


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest):
    result = analyze_text(request.text)

    return AnalyzeResponse(
        success=True,
        entityCount=result["entityCount"],
        maskedText=result["maskedText"],
        entities=[EntityResult(**e) for e in result["entities"]],
    )


@router.post("/api/scan", response_model=ScanResponse)
def scan_prompt(request: ScanRequest):
    result = analyze_text(request.prompt)

    # ECI runs on the already-masked text (never the raw prompt), and on
    # every request - not just when Presidio finds entities - since it
    # catches enterprise-context risk (e.g. "explain our OAuth2
    # implementation") that contains no PII at all. classify() never
    # raises; on any failure it returns a fail-closed fallback dict.
    eci_result = ECIResult(**classify_context(result["maskedText"]))

    if result["entityCount"] == 0:
        return ScanResponse(status="SAFE", sanitizedPrompt=request.prompt, eci=eci_result)

    entity_types = ", ".join(sorted({entity["entity_type"] for entity in result["entities"]}))
    reason = f"Detected {result['entityCount']} sensitive item(s): {entity_types}"
    issues = [
        {
            "entityType": entity["entity_type"],
            "value": entity["value"],
            "score": entity["score"],
        }
        for entity in result["entities"]
    ]

    return ScanResponse(
        status="SANITIZE",
        sanitizedPrompt=result["maskedText"],
        reason=reason,
        issues=issues,
        eci=eci_result,
    )
