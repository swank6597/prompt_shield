# routes.py
# API route definitions. Currently exposes the Presidio-only /analyze
# endpoint (merged from the POC's api.py) plus /health. Once regex/ and
# ai/ layers are wired in, this becomes the orchestration point that runs
# Regex -> Presidio -> ECI -> Policy Engine and returns the final decision.

from fastapi import APIRouter

from models import AnalyzeRequest, AnalyzeResponse, EntityResult, ScanRequest, ScanResponse
from presidio.presidio_engine import analyze_text

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

    if result["entityCount"] == 0:
        return ScanResponse(status="SAFE", sanitizedPrompt=request.prompt)

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
    )
