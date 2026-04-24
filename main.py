"""
Atomic Choice — FastAPI application entry point.

Изменения:
  - При старте генерируются (или загружаются) 10 keypair.
    Приватные ключи → keys.txt (для распределения участникам).
    Публичные адреса → добавляются в глобальный вайтлист автоматически.
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
    logger.info(" Atomic Choice — starting up")
    logger.info("━" * 60)

    # ── Шаг 1: Инициализация keypairs ─────────────────────────────────────────
    from app.core.keys import initialize_keys
    from app.models.student import add_keypair_participant

    keypairs = initialize_keys()
    logger.info("Keys ready: %d keypairs (keys.txt — раздать участникам)", len(keypairs))

    # Регистрируем всех keypair-участников в реестре студентов
    for kp in keypairs:
        add_keypair_participant(kp["wallet"], kp["private_key"], kp["index"])

    # ── Шаг 2: Загрузка деплоев ───────────────────────────────────────────────
    d = load_deployments()
    if d:
        settings.FACTORY_ADDRESS   = d.get("factory")
        settings.WHITELIST_ADDRESS = d.get("whitelist")
        settings.VERIFIER_ADDRESS  = d.get("verifier")
        settings.POSEIDON_ADDRESS  = d.get("poseidon")
        logger.info("Loaded deployments: factory=%s", settings.FACTORY_ADDRESS)

        # ── Шаг 3: Синхронизация Merkle tree ──────────────────────────────────
        if is_connected() and settings.WHITELIST_ADDRESS:
            try:
                from app.services.whitelist_service import sync_tree_from_chain
                await sync_tree_from_chain()
            except Exception as e:
                logger.warning("Could not sync Merkle tree: %s", e)

        # ── Шаг 4: Автоматический вайтлист keypair-участников ─────────────────
        #    Если контракты уже задеплоены — добавляем keypair-участников
        #    в глобальный вайтлист (тех, кого ещё нет).
        if is_connected() and settings.WHITELIST_ADDRESS:
            try:
                await _whitelist_keypair_participants(keypairs)
            except Exception as e:
                logger.warning("Could not auto-whitelist keypair participants: %s", e)
    else:
        logger.info("No deployments found — visit /api/admin/setup to initialize")
        logger.info(
            "После деплоя запустите /api/admin/whitelist/keypairs "
            "чтобы добавить 10 участников в вайтлист"
        )

    connected = is_connected()
    logger.info("Hardhat node: %s", "✓ connected" if connected else "✗ not connected")
    logger.info("Open: http://localhost:8000")
    logger.info("Keys file: keys.txt")
    logger.info("━" * 60)

    yield

    logger.info("Atomic Choice shutting down.")


async def _whitelist_keypair_participants(keypairs: list[dict]):
    """
    Добавляет всех keypair-участников в глобальный вайтлист.
    Пропускает уже добавленных.
    """
    from app.models.student import get_by_wallet
    from app.services.whitelist_service import add_student_to_whitelist

    added = 0
    for kp in keypairs:
        student = get_by_wallet(kp["wallet"])
        if student and not student.whitelisted:
            try:
                await add_student_to_whitelist(kp["wallet"])
                added += 1
            except Exception as e:
                logger.debug("Skip keypair whitelist %s: %s", kp["wallet"][:10], e)

    if added:
        logger.info("Auto-whitelisted %d keypair participants", added)


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
