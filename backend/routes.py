# routes.py
# API route definitions. Currently exposes the Presidio-only /analyze
# endpoint (merged from the POC's api.py) plus /health. Once regex/ and
# ai/ layers are wired in, this becomes the orchestration point that runs
# Regex -> Presidio -> ECI -> Policy Engine and returns the final decision.

from fastapi import APIRouter

from models import AnalyzeRequest, AnalyzeResponse, EntityResult
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
