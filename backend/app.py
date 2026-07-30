# app.py
# FastAPI application entrypoint. Creates the app instance and registers
# routes.py. Merged from the POC's api.py (FastAPI() app metadata).
# Run with: uvicorn app:app --reload

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import config
from routes import router
from auth.routes import auth_router, device_router

# ---------------------------------------------------------------------------
# CORS: the scan API and the auth/device-management API are different trust
# boundaries and need different origin policies (specs/authentication/'s
# Requirement 8.1) - but FastAPI/Starlette only lets one CORSMiddleware own
# preflight handling for the whole app it wraps, so a single global
# CORSMiddleware can't express two different allow_origins lists. Instead,
# each surface is its own sub-app with its own CORSMiddleware, mounted under
# a distinct prefix; Starlette tries mounts in registration order and a
# root ("/") mount matches everything, so the scan sub-app - which must
# serve unprefixed paths like /health and /api/scan - is mounted LAST, after
# the more specific /auth and /devices prefixes.
# ---------------------------------------------------------------------------

# The Chrome extension's content script runs on chatgpt.com and calls this
# API cross-origin - without CORS the browser blocks the request before it
# even reaches routes.py. chrome-extension:// origins have a per-install
# random ID, so for hackathon purposes this allows all origins rather than
# hardcoding one; tighten this before any real deployment.
scan_app = FastAPI(
    title="PromptShield Detection API",
    description="PromptShield backend - Regex + Presidio + Enterprise Context Intelligence + Policy Engine",
    version="1.0.0",
)
scan_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
scan_app.include_router(router)

# /auth/* - login/session/audit-log. No wildcard: PROMPTSHIELD_AUTH_ALLOWED_ORIGINS
# is empty until a real dashboard origin exists to allow-list.
auth_app = FastAPI()
auth_app.add_middleware(
    CORSMiddleware,
    allow_origins=config.AUTH_ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
auth_app.include_router(auth_router)

# /devices/* - enrollment/listing/revocation. Same policy as /auth/*.
devices_app = FastAPI()
devices_app.add_middleware(
    CORSMiddleware,
    allow_origins=config.AUTH_ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
devices_app.include_router(device_router)

# docs_url/redoc_url/openapi_url=None: FastAPI adds its own /docs, /redoc,
# /openapi.json routes to every app instance at construction time - those
# would be registered on `app` itself BEFORE the mounts below and would
# therefore intercept those exact paths first, showing an empty schema and
# making scan_app's own (real) /docs unreachable. Disabling the outer app's
# copies lets requests for /docs etc. fall through to the "/" mount, so
# Swagger UI at /docs shows the scan API as before; /auth/docs and
# /devices/docs show those APIs via their own sub-app instances.
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

app.mount("/auth", auth_app)
app.mount("/devices", devices_app)
app.mount("/", scan_app)  # must be last: "/" matches every path
