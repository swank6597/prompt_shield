# models.py
# Pydantic request/response models for the API. Merged from the POC's
# api.py (AnalyzeRequest, EntityResult, AnalyzeResponse). Shared across
# routes.py and (eventually) the AnalysisResult shape all three analyzer
# layers - regex, presidio, ECI - should conform to before hitting policy/.

from typing import List
from pydantic import BaseModel


class AnalyzeRequest(BaseModel):
    text: str


class EntityResult(BaseModel):
    entity_type: str
    value: str
    score: float
    start: int
    end: int


class AnalyzeResponse(BaseModel):
    success: bool
    entityCount: int
    maskedText: str
    entities: List[EntityResult]


class ScanRequest(BaseModel):
    prompt: str


class ScanIssue(BaseModel):
    entityType: str
    value: str
    score: float


class ECIResult(BaseModel):
    intent: str
    documentType: str
    requiresEnterpriseKnowledge: bool
    containsInternalArchitecture: bool
    containsImplementationDetails: bool
    containsSourceCode: bool
    containsCustomerData: bool
    containsSecrets: bool
    confidence: float
    reasoning: List[str]


class ScanResponse(BaseModel):
    status: str
    sanitizedPrompt: str | None = None
    reason: str | None = None
    issues: List[ScanIssue] = []
    eci: ECIResult | None = None
    riskScore: int | None = None
    matchedRules: List[str] = []
