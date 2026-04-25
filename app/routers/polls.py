"""
Polls router.

Новые эндпоинты:
  POST /api/polls/{address}/whitelist
    — создатель добавляет участника в вайтлист своего голосования

  GET /api/polls/{address}/whitelist
    — список участников в вайтлисте голосования

  GET /api/polls/{address}/results
    — результаты (только если голосование завершено)
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.poll_service import get_all_polls, get_poll, cast_vote, build_vote_message
from app.services.whitelist_service import get_merkle_proof_for_wallet
from app.schemas.poll import VoteRequest
from app.core.blockchain import is_connected
import logging

logger = logging.getLogger("atomic-choice.polls_router")
router = APIRouter(prefix="/api", tags=["polls"])


class PollWhitelistRequest(BaseModel):
    voter_wallet: str
    requester_wallet: str  # должен совпадать с создателем голосования


# ── Polls list ────────────────────────────────────────────────────────────────

@router.get("/polls")
async def list_polls():
    if not is_connected():
        raise HTTPException(status_code=503, detail="Hardhat node not connected")
    try:
        polls = await get_all_polls(reveal_results=False)
        return {"polls": polls, "total": len(polls)}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("list_polls error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/polls/{address}")
async def get_poll_detail(address: str):
    """
    Детали голосования.
    Результаты скрыты если голосование активно.
    """
    try:
        poll = await get_poll(address, reveal_results=False)
        return poll
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/polls/{address}/results")
async def get_poll_results(address: str):
    """
    Результаты голосования.
    Доступны только после завершения голосования (status == 'ended').
    """
    try:
        poll = await get_poll(address, reveal_results=True)
        if poll["status"] == "active":
            raise HTTPException(
                status_code=403,
                detail="Результаты скрыты до завершения голосования. "
                       f"Голосование заканчивается в {poll['end_time']}."
            )
        return {
            "poll_id":     poll["poll_id"],
            "title":       poll["title"],
            "status":      poll["status"],
            "total_votes": poll["total_votes"],
            "options":     poll["options"],
            "results":     poll["results"],
            "percentages": poll["percentages"],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Per-poll whitelist ────────────────────────────────────────────────────────

@router.get("/polls/{address}/whitelist")
async def get_poll_whitelist(address: str):
    """Список участников в вайтлисте голосования."""
    from app.services.poll_whitelist_service import (
        get_poll_creator, get_poll_members, get_poll_tree
    )
    creator = get_poll_creator(address)
    members = get_poll_members(address)
    tree    = get_poll_tree(address)
    return {
        "poll":      address,
        "creator":   creator,
        "count":     len(members),
        "members":   members,
        "tree_root": str(tree.root()) if tree and tree.leaves else None,
    }


@router.post("/polls/{address}/whitelist")
async def add_to_poll_whitelist(address: str, req: PollWhitelistRequest):
    """
    Создатель голосования добавляет участника в вайтлист своего голосования.

    requester_wallet должен совпадать с кошельком создателя.
    В demo-режиме проверяется только сравнение строк (без крипто-подписи).
    """
    from app.services.poll_whitelist_service import add_wallet_to_poll_whitelist
    try:
        result = await add_wallet_to_poll_whitelist(
            poll_address=address,
            voter_wallet=req.voter_wallet,
            requester_wallet=req.requester_wallet,
        )
        return result
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Vote ──────────────────────────────────────────────────────────────────────

@router.get("/vote/message")
async def vote_message(poll_address: str, option_index: int, nonce: str):
    """
    Возвращает каноническое сообщение для подписи приватным ключом.
    Используется фронтендом перед вызовом personal_sign.
    """
    return {"message": build_vote_message(poll_address, option_index, nonce)}


@router.post("/vote")
async def vote(req: VoteRequest):
    try:
        result = await cast_vote(
            poll_address=req.poll_address,
            option_index=req.option_index,
            voter_wallet=req.wallet,
            signature=req.signature,
            message=req.message,
            nonce=req.nonce,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error("vote error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── Merkle proof ──────────────────────────────────────────────────────────────

@router.get("/merkle-proof/{wallet}")
async def merkle_proof(wallet: str):
    try:
        return get_merkle_proof_for_wallet(wallet)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/merkle-proof/{poll_address}/{wallet}")
async def merkle_proof_for_poll(poll_address: str, wallet: str):
    """Merkle proof из per-poll дерева (или глобального как fallback)."""
    from app.services.poll_whitelist_service import get_poll_merkle_proof
    try:
        return get_poll_merkle_proof(poll_address, wallet)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
