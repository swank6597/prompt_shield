# policy_engine.py
# Deterministic, rule-based decision engine. Consumes the merged AnalysisResult
# from Regex/Presidio/ECI analyzers and rules.json to produce a final decision
# (Allow/Warn/Mask/Block) plus a user-friendly explanation. No AI involved.
