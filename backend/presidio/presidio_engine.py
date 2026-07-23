# presidio_engine.py
# Layer 2 detection - wraps Microsoft Presidio Analyzer/Anonymizer to detect
# and mask PII (names, emails, phone numbers, credit cards, addresses, etc.)
# plus custom enterprise/India-specific entities registered via recognizers/.
#
# This module is intentionally FastAPI-agnostic: routes.py calls into it,
# it does not know about HTTP. Merged from the standalone Presidio POC's
# api.py (analyzer/anonymizer setup + core analyze logic).

from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

from presidio.recognizers.registry import register_all
from utils.logger import get_logger

log = get_logger("presidio")

# Minimum confidence score to keep a detection (filters out low-confidence noise).
MIN_SCORE = 0.85

# ----------------------------------------------------
# Initialize Presidio (runs once, at import time)
# ----------------------------------------------------
log.info("Initializing Presidio AnalyzerEngine (this loads the spaCy NLP model)...")
analyzer = AnalyzerEngine()
register_all(analyzer)
log.info("Presidio ready: %d recognizers registered", len(analyzer.registry.recognizers))

anonymizer = AnonymizerEngine()


def analyze_text(text: str) -> dict:
    """
    Runs Presidio analysis + anonymization on the given text.

    Returns a plain dict (not a pydantic model) so this module has no
    dependency on backend/models.py - routes.py is responsible for
    wrapping this into the AnalyzeResponse schema.

    Shape:
        {
            "entityCount": int,
            "maskedText": str,
            "entities": [
                {"entity_type": str, "value": str, "score": float,
                 "start": int, "end": int},
                ...
            ]
        }
    """
    results = analyzer.analyze(text=text, language="en")
    log.debug("Raw analyzer results: %d (before min-score filter)", len(results))

    # Filter out low-confidence detections
    below_threshold = [r for r in results if r.score < MIN_SCORE]
    if below_threshold:
        log.debug(
            "Dropped %d low-confidence detection(s) below MIN_SCORE=%.2f: %s",
            len(below_threshold), MIN_SCORE,
            [(r.entity_type, round(r.score, 2)) for r in below_threshold],
        )
    results = [r for r in results if r.score >= MIN_SCORE]

    anonymized = anonymizer.anonymize(text=text, analyzer_results=results)

    entities = [
        {
            "entity_type": r.entity_type,
            "value": text[r.start:r.end],
            "score": round(r.score, 2),
            "start": r.start,
            "end": r.end,
        }
        for r in results
    ]

    return {
        "entityCount": len(entities),
        "maskedText": anonymized.text,
        "entities": entities,
    }
