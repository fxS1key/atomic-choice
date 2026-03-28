"""
Admin router — deploy, whitelist management, seed data.
"""
from fastapi import APIRouter, HTTPException
from app.services.deploy_service import deploy_all
from app.services.whitelist_service import (
    add_student_to_whitelist,
    add_all_students_to_whitelist,
    get_whitelist_info,
    sync_tree_from_chain,
)
from app.services.poll_service import seed_polls, create_poll
from app.models.student import get_all, add_student
from app.schemas.poll import AddStudentRequest, PollCreate
from app.core.blockchain import is_connected, load_deployments
import logging

logger = logging.getLogger("atomic-choice.admin")
router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/status")
async def get_status():
    connected = is_connected()
    deployments = load_deployments()
    students = get_all()
    whitelisted = sum(1 for s in students if s.whitelisted)
    return {
        "node_connected": connected,
        "contracts_deployed": bool(deployments),
        "deployments": deployments,
        "students_total": len(students),
        "students_whitelisted": whitelisted,
    }


@router.post("/deploy")
async def deploy_contracts():
    """Deploy all contracts to local Hardhat node."""
    try:
        result = await deploy_all()
        return {"ok": True, "deployments": result}
    except Exception as e:
        logger.error("Deploy failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/setup")
async def full_setup():
    """
    One-click setup:
    1. Deploy contracts
    2. Add all seed students to whitelist
    3. Create seed polls
    """
    try:
        deployments = await deploy_all()
        whitelist_results = await add_all_students_to_whitelist()
        poll_results = await seed_polls()
        return {
            "ok": True,
            "deployments": deployments,
            "whitelist": whitelist_results,
            "polls": poll_results,
        }
    except Exception as e:
        logger.error("Setup failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


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


@router.post("/students")
async def add_student_endpoint(req: AddStudentRequest):
    student = add_student(req.wallet, req.name, req.group)
    return {
        "ok": True,
        "wallet": student.wallet,
        "commitment": hex(student.commitment),
    }


@router.post("/polls/seed")
async def create_seed_polls():
    results = await seed_polls()
    return {"ok": True, "polls": results}


@router.post("/polls")
async def create_poll_endpoint(req: PollCreate):
    try:
        result = await create_poll(
            title=req.title,
            description=req.description,
            options=req.options,
            start_offset_seconds=req.start_offset_seconds,
            duration_seconds=req.duration_seconds,
        )
        return {"ok": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync")
async def sync_tree():
    """Re-sync Merkle tree from on-chain events."""
    await sync_tree_from_chain()
    return {"ok": True, "message": "Tree synced"}
