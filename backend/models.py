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
