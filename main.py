"""
Atomic Choice — FastAPI application entry point.
"""
import logging
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.blockchain import is_connected, load_deployments
from app.routers import admin, polls, students, pages

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("atomic-choice")


# ── Startup ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("━" * 60)
    logger.info("  Atomic Choice — starting up")
    logger.info("━" * 60)

    # Try to load existing deployments
    d = load_deployments()
    if d:
        settings.FACTORY_ADDRESS   = d.get("factory")
        settings.WHITELIST_ADDRESS = d.get("whitelist")
        settings.VERIFIER_ADDRESS  = d.get("verifier")
        settings.POSEIDON_ADDRESS  = d.get("poseidon")
        logger.info("Loaded deployments: factory=%s", settings.FACTORY_ADDRESS)

        # Sync Merkle tree from chain
        if is_connected() and settings.WHITELIST_ADDRESS:
            try:
                from app.services.whitelist_service import sync_tree_from_chain
                await sync_tree_from_chain()
            except Exception as e:
                logger.warning("Could not sync Merkle tree: %s", e)
    else:
        logger.info("No deployments found — visit /api/admin/setup to initialize")

    connected = is_connected()
    logger.info("Hardhat node: %s", "✓ connected" if connected else "✗ not connected")
    logger.info("Open: http://localhost:8000")
    logger.info("━" * 60)

    yield

    logger.info("Atomic Choice shutting down.")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.APP_TITLE,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
static_dir = Path("static")
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Routers
app.include_router(pages.router)
app.include_router(polls.router)
app.include_router(students.router)
app.include_router(admin.router)
