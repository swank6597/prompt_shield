# app.py
# FastAPI application entrypoint. Creates the app instance and registers
# routes.py. Merged from the POC's api.py (FastAPI() app metadata).
# Run with: uvicorn app:app --reload

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes import router

app = FastAPI(
    title="PromptShield Detection API",
    description="PromptShield backend - Regex + Presidio + Enterprise Context Intelligence + Policy Engine",
    version="1.0.0",
)

# The Chrome extension's content script runs on chatgpt.com and calls this
# API cross-origin - without this, the browser blocks the request before
# it even reaches routes.py. chrome-extension:// origins have a per-install
# random ID, so for hackathon purposes we allow all origins rather than
# hardcoding one; tighten this before any real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)