"""
Admin router — deploy, whitelist, регистрации, seed.

Все эндпоинты защищены `X-Admin-Token`.
Токен пишется в admin_token.txt при старте (или берётся из .env).
"""
from fastapi import APIRouter, Depends, HTTPException
from app.services.deploy_service import deploy_all
from app.services.whitelist_service import (
    add_student_to_whitelist,
    add_all_students_to_whitelist,
    get_whitelist_info,
    sync_tree_from_chain,
)
from app.services.poll_service import seed_polls, create_poll
from app.services.user_service import (
    pending_users, approved_users, approve_user, sync_users_to_registry,
)
from app.models.student import get_all, add_student, get_by_wallet
from app.schemas.poll import AddStudentRequest, PollCreate, PollCreateWithCreator
from app.core.blockchain import is_connected, load_deployments
from app.core.keys import get_keypairs
from app.core.admin_auth import require_admin
from app.core.config import settings
import logging

logger = logging.getLogger("atomic-choice.admin")
router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/status")
async def get_status():
    connected   = is_connected()
    deployments = load_deployments()
    students    = get_all()
    whitelisted = sum(1 for s in students if s.whitelisted)
    keypairs    = get_keypairs()
    pending     = pending_users()
    approved    = approved_users()
    return {
        "node_connected":       connected,
        "contracts_deployed":   bool(deployments),
        "deployments":          deployments,
        "students_total":       len(students),
        "students_whitelisted": whitelisted,
        "keypairs_generated":   len(keypairs),
        "keys_file":            "keys.txt",
        "users_pending":        len(pending),
        "users_approved":       len(approved),
        "public_url":           settings.PUBLIC_URL,
    }


@router.post("/deploy")
async def deploy_contracts():
    """Деплой всех контрактов в локальный Hardhat node."""
    try:
        result = await deploy_all()
        return {"ok": True, "deployments": result}
    except Exception as e:
        logger.error("Deploy failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/setup")
async def full_setup():
    """
    Демонстрационный one-click setup:
    1. Деплой контрактов
    2. Глобальный whitelist для seed-студентов и keypair-участников
    3. Тестовые опросы
    """
    try:
        deployments       = await deploy_all()
        whitelist_results = await add_all_students_to_whitelist()
        keypair_results   = await _whitelist_all_keypairs()
        poll_results      = await seed_polls()
        return {
            "ok":          True,
            "deployments": deployments,
            "whitelist":   whitelist_results,
            "keypairs":    keypair_results,
            "polls":       poll_results,
        }
    except Exception as e:
        logger.error("Setup failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── Whitelist ────────────────────────────────────────────────────────────────

@router.get("/whitelist")
async def whitelist_info():
    try:
        return await get_whitelist_info()
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/whitelist/{wallet}")
async def add_to_whitelist(wallet: str):
    try:
        result = await add_student_to_whitelist(wallet)
        return {"ok": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/whitelist/batch/all")
async def add_all_to_whitelist():
    results = await add_all_students_to_whitelist()
    return {"ok": True, "results": results}


@router.post("/whitelist/keypairs")
async def whitelist_keypair_participants():
    """Добавляет все keypair-участники в глобальный вайтлист."""
    results = await _whitelist_all_keypairs()
    return {"ok": True, "results": results}


@router.get("/keypairs")
async def list_keypairs():
    pairs = get_keypairs()
    return {
        "count":     len(pairs),
        "keys_file": "keys.txt",
        "participants": [
            {"index": p["index"], "wallet": p["wallet"], "commitment": p["commitment"]}
            for p in pairs
        ],
    }


# ── Registered users ─────────────────────────────────────────────────────────

@router.get("/users/pending")
async def list_pending_users():
    return {"users": pending_users()}


@router.get("/users/approved")
async def list_approved_users():
    return {"users": approved_users()}


@router.post("/users/{wallet}/approve")
async def approve(wallet: str):
    try:
        return await approve_user(wallet)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("approve failed for %s: %s", wallet, e)
        raise HTTPException(status_code=500, detail=str(e))


# ── Manual student registration (legacy) ─────────────────────────────────────

@router.post("/students")
async def add_student_endpoint(req: AddStudentRequest):
    student = add_student(req.wallet, req.name, req.group)
    return {"ok": True, "wallet": student.wallet, "commitment": hex(student.commitment)}


# ── Polls ────────────────────────────────────────────────────────────────────

@router.post("/polls/seed")
async def create_seed_polls():
    results = await seed_polls()
    return {"ok": True, "polls": results}


@router.post("/polls")
async def create_poll_endpoint(req: PollCreateWithCreator):
    try:
        result = await create_poll(
            title=req.title,
            description=req.description,
            options=req.options,
            start_offset_seconds=req.start_offset_seconds,
            duration_seconds=req.duration_seconds,
            creator_wallet=req.creator_wallet,
        )
        return {"ok": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync")
async def sync_tree():
    """Re-sync Merkle tree from on-chain events."""
    await sync_tree_from_chain()
    sync_users_to_registry()
    return {"ok": True, "message": "Tree synced"}


# ── Internal ─────────────────────────────────────────────────────────────────

async def _whitelist_all_keypairs() -> list[dict]:
    """Добавляет всех keypair-участников в глобальный вайтлист."""
    keypairs = get_keypairs()
    results  = []
    for kp in keypairs:
        student = get_by_wallet(kp["wallet"])
        if not student:
            results.append({"wallet": kp["wallet"], "ok": False, "error": "not in registry"})
            continue
        if student.whitelisted:
            results.append({"wallet": kp["wallet"], "ok": True, "skipped": "already whitelisted"})
            continue
        try:
            r = await add_student_to_whitelist(kp["wallet"])
            results.append({"wallet": kp["wallet"], "ok": True, **r})
        except Exception as e:
            logger.error("Failed to whitelist keypair %s: %s", kp["wallet"], e)
            results.append({"wallet": kp["wallet"], "ok": False, "error": str(e)})
    return results
