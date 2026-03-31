"""FastAPI application — entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import agent, backtest, data, health, market, portfolio, risk, signals, ws
from app.config import settings
from app.services.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("Starting Trading Agent Platform...")
    if settings.environment != "test":
        start_scheduler()
    yield
    stop_scheduler()
    logger.info("Trading Agent Platform stopped.")


app = FastAPI(
    title="Agentic Trading Platform",
    description="Autonomous AI trading agent with signal generation, risk management, and backtesting.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global error handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Register routers
app.include_router(health.router)
app.include_router(signals.router, prefix="/api")
app.include_router(agent.router, prefix="/api")
app.include_router(portfolio.router, prefix="/api")
app.include_router(risk.router, prefix="/api")
app.include_router(market.router, prefix="/api")
app.include_router(backtest.router, prefix="/api")
app.include_router(data.router, prefix="/api")
app.include_router(ws.router)

# Serve React frontend if built assets are present (production)
_FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "frontend_dist")
_FRONTEND_DIR = os.path.abspath(_FRONTEND_DIR)

if os.path.isdir(_FRONTEND_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(_FRONTEND_DIR, "assets")), name="assets")

    @app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(_FRONTEND_DIR, "index.html"))

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """SPA fallback — serve index.html for all non-API routes."""
        file_path = os.path.join(_FRONTEND_DIR, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(_FRONTEND_DIR, "index.html"))
else:
    @app.get("/")
    async def root():
        return {"message": "Trading Agent API", "docs": "/docs", "health": "/health"}
