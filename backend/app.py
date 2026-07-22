# app.py
# FastAPI application entrypoint. Creates the app instance and registers
# routes.py. Merged from the POC's api.py (FastAPI() app metadata).
# Run with: uvicorn app:app --reload

from fastapi import FastAPI

from routes import router

app = FastAPI(
    title="PromptShield Detection API",
    description="PromptShield backend - Regex + Presidio + Enterprise Context Intelligence + Policy Engine",
    version="1.0.0",
)

app.include_router(router)
