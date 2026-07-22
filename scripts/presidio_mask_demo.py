# presidio_mask_demo.py
# Interactive CLI for manually testing Presidio detection + masking,
# including custom recognizers (banking.py, personal.py, etc. via
# register_all). Merged from two POC console scripts (mask_demo.py and
# app.py) - kept the more complete version: multi-line input, registered
# custom recognizers, and per-entity score printout before masking.
# Not part of the served API - pure manual sanity-check tool.
#
# Run from repo root with backend/ on the path, e.g.:
#   PYTHONPATH=backend python scripts/presidio_mask_demo.py

from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

from presidio.recognizers.registry import register_all

analyzer = AnalyzerEngine()
register_all(analyzer)

anonymizer = AnonymizerEngine()

print("Enter text (type END on a new line to finish):")

lines = []
while True:
    line = input()
    if line == "END":
        break
    lines.append(line)

text = "\n".join(lines)

results = analyzer.analyze(text=text, language="en")

print("\nDetected Entities:")
for r in results:
    print(f"{r.entity_type}: {text[r.start:r.end]} ({r.score:.2f})")

masked_text = anonymizer.anonymize(text=text, analyzer_results=results)

print("\nMasked Text:")
print(masked_text.text)
