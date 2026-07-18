from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.capabilities import router as capabilities_router
from backend.app.api.health import router as health_router
from backend.app.api.runs import router as runs_router
from backend.app.api.venue import router as venue_router
from backend.app.config import settings
from backend.app.logging import setup_logging

setup_logging(settings.LOG_LEVEL)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield


app = FastAPI(
    title="CrowdCue 2.0 API",
    description="GenAI Stadium Guidance Preflight and Operational Decision Support",
    version="2.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Session-ID", "Idempotency-Key"],
)
app.include_router(health_router)
app.include_router(capabilities_router)
app.include_router(venue_router)
app.include_router(runs_router)


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "app": "CrowdCue 2.0",
        "description": "Guidance Preflight and Operational Decision Support",
        "status": "RUNNING",
        "synthetic_prototype": True,
    }
