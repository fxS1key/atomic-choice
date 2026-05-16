"""
Polls router.

Новые эндпоинты:
  POST /api/polls
    — создание опроса авторизованным пользователем (US3)
  POST /api/polls/{address}/whitelist
    — создатель добавляет участника в вайтлист своего голосования
  GET /api/polls/{address}/whitelist
    — список участников в вайтлисте голосования
  GET /api/polls/{address}/results
    — результаты (только если голосование завершено)
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from app.services.poll_service import (
    get_all_polls, get_poll, cast_vote, build_vote_message, create_poll,
)
from app.services.whitelist_service import get_merkle_proof_for_wallet
from app.schemas.poll import VoteRequest, PollCreate
from app.core.blockchain import is_connected
from app.routers.auth import current_user
import logging

logger = logging.getLogger("atomic-choice.polls_router")
router = APIRouter(prefix="/api", tags=["polls"])


class PollWhitelistRequest(BaseModel):
    voter_wallet: str
    requester_wallet: str | None = None  # если не задан — берём из cookie-сессии


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


@router.post("/polls")
async def create_poll_authenticated(req: PollCreate, request: Request):
    """
    Создание опроса авторизованным пользователем.
    Реализует User Story №3: создатель = текущая сессия.
    Поля валидируются Pydantic'ом (минимум 2 варианта, заголовок ≥3 символа).
    """
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Войдите, чтобы создавать опросы")
    if not user.get("approved"):
        raise HTTPException(
            status_code=403,
            detail="Только верифицированные участники могут создавать опросы. "
                   "Дождитесь, пока администратор добавит вас в вайтлист."
        )
    if not is_connected():
        raise HTTPException(status_code=503, detail="Hardhat нода недоступна")

    # Бизнес-валидации поверх Pydantic
    if any(not o.strip() for o in req.options):
        raise HTTPException(status_code=400, detail="Все варианты ответа должны быть заполнены")
    if len(req.options) < 2:
        raise HTTPException(status_code=400, detail="Минимум два варианта ответа")
    if req.duration_seconds < 60:
        raise HTTPException(status_code=400, detail="Длительность не может быть меньше минуты")

    try:
        result = await create_poll(
            title=req.title.strip(),
            description=req.description.strip(),
            options=[o.strip() for o in req.options],
            start_offset_seconds=req.start_offset_seconds,
            duration_seconds=req.duration_seconds,
            creator_wallet=user["wallet"],
        )
        return {"ok": True, **result}
    except Exception as e:
        logger.error("create_poll error: %s", e)
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


class PollSyncRequest(BaseModel):
    requester_wallet: str | None = None


@router.post("/polls/{address}/whitelist/sync")
async def sync_poll_whitelist(address: str, request: Request):
    """
    Создатель голосования принудительно публикует текущий off-chain
    корень своего per-poll вайтлиста в контракт. Решает ошибку
    «Merkle root не принят контрактом».

    Право вызова — текущий залогиненный пользователь должен быть создателем
    голосования (per-poll registry).
    """
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Войдите, чтобы обновить вайтлист")
    from app.services.poll_whitelist_service import sync_poll_root
    try:
        result = await sync_poll_root(address, requester_wallet=user["wallet"])
        return result
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/polls/{address}/whitelist")
async def add_to_poll_whitelist(
    address: str, req: PollWhitelistRequest, request: Request
):
    """
    Создатель голосования добавляет участника в вайтлист своего голосования.

    requester_wallet должен совпадать с кошельком создателя.
    Если поле опущено — берём кошелёк из текущей сессии.
    """
    requester = req.requester_wallet
    if not requester:
        user = current_user(request)
        if not user:
            raise HTTPException(status_code=401, detail="Войдите, чтобы управлять вайтлистом")
        requester = user["wallet"]
    from app.services.poll_whitelist_service import add_wallet_to_poll_whitelist
    try:
        result = await add_wallet_to_poll_whitelist(
            poll_address=address,
            voter_wallet=req.voter_wallet,
            requester_wallet=requester,
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
async def vote(req: VoteRequest, request: Request):
    """
    Голосование. Два сценария:

    1) Запрос содержит signature/message/nonce → классическая EIP-191 проверка
       (для скриптов и тестов).
    2) Только poll_address + option_index → подпись делается сервером от имени
       текущего залогиненного пользователя. Это основной путь для UI.
    """
    try:
        if req.signature and req.message and req.nonce:
            result = await cast_vote(
                poll_address=req.poll_address,
                option_index=req.option_index,
                voter_wallet=req.wallet,
                signature=req.signature,
                message=req.message,
                nonce=req.nonce,
            )
        else:
            user = current_user(request)
            if not user:
                raise HTTPException(status_code=401, detail="Войдите, чтобы голосовать")
            # Сервер сам подписывает сообщение приватным ключом пользователя.
            # Этот PK был детерминированно выведен из пароля при регистрации.
            from eth_account import Account
            from eth_account.messages import encode_defunct
            import secrets as _secrets
            nonce   = _secrets.token_hex(8)
            message = build_vote_message(req.poll_address, req.option_index, nonce)
            signed  = Account.sign_message(
                encode_defunct(text=message),
                private_key=user["private_key"],
            )
            result = await cast_vote(
                poll_address=req.poll_address,
                option_index=req.option_index,
                voter_wallet=user["wallet"],
                signature=signed.signature.hex(),
                message=message,
                nonce=nonce,
            )
        return result
    except HTTPException:
        raise
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
