from fastapi import APIRouter, HTTPException
from app.services.poll_service import get_all_polls, get_poll, cast_vote
from app.services.whitelist_service import get_merkle_proof_for_wallet
from app.schemas.poll import VoteRequest
from app.core.blockchain import is_connected
import logging

logger = logging.getLogger("atomic-choice.polls_router")
router = APIRouter(prefix="/api", tags=["polls"])


@router.get("/polls")
async def list_polls():
    if not is_connected():
        raise HTTPException(status_code=503, detail="Hardhat node not connected")
    try:
        polls = await get_all_polls()
        return {"polls": polls, "total": len(polls)}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("list_polls error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/polls/{address}")
async def get_poll_detail(address: str):
    try:
        poll = await get_poll(address)
        return poll
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/vote")
async def vote(req: VoteRequest):
    try:
        result = await cast_vote(req.poll_address, req.option_index, req.wallet)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error("vote error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/merkle-proof/{wallet}")
async def merkle_proof(wallet: str):
    try:
        return get_merkle_proof_for_wallet(wallet)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
