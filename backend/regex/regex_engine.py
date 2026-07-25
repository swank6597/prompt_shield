# regex_engine.py
# Layer 1 detection - runs deterministic regex patterns over the prompt to
# find secrets (API keys, tokens, passwords, connection strings, IPs, PAN,
# Aadhaar, etc.) with no AI involved. Returns matches in the shared AnalysisResult shape.
