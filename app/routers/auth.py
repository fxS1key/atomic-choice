"""
Эндпоинты регистрации, логина и текущей сессии.

POST /api/auth/register   { nick, password }  → user + Set-Cookie ac_session
POST /api/auth/login      { nick, password }  → user + Set-Cookie ac_session
POST /api/auth/logout                          → очищает cookie
GET  /api/auth/me                              → текущий пользователь (или 401)
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.core import auth as auth_core
from app.services.user_service import register_user_in_registry
from app.models.student import get_by_wallet

logger = logging.getLogger("atomic-choice.auth_router")
router = APIRouter(prefix="/api/auth", tags=["auth"])

COOKIE_NAME = "ac_session"


class Credentials(BaseModel):
    nick:     str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=auth_core.PASSWORD_MIN, max_length=128)


def _set_session_cookie(resp: Response, wallet: str):
    token = auth_core.issue_session_token(wallet)
    resp.set_cookie(
        COOKIE_NAME, token,
        max_age=auth_core.SESSION_TTL,
        httponly=True,
        samesite="lax",
        path="/",
    )


def _user_view_with_state(user: dict) -> dict:
    """user_public_view + актуальный whitelist-флаг из student-реестра."""
    view = auth_core.user_public_view(user)
    s = get_by_wallet(user["wallet"])
    view["whitelisted"] = bool(s and s.whitelisted)
    view["approved"]    = bool(user.get("approved")) or view["whitelisted"]
    return view


@router.post("/register")
async def register(req: Credentials, response: Response):
    try:
        user = auth_core.register(req.nick, req.password)
    except auth_core.AuthError as e:
        raise HTTPException(status_code=400, detail=str(e))
    register_user_in_registry(user)
    _set_session_cookie(response, user["wallet"])
    logger.info("register | nick=%s wallet=%s", user["nick"], user["wallet"])
    return {"ok": True, "user": _user_view_with_state(user)}


@router.post("/login")
async def login(req: Credentials, response: Response):
    try:
        user = auth_core.login(req.nick, req.password)
    except auth_core.AuthError as e:
        raise HTTPException(status_code=401, detail=str(e))
    register_user_in_registry(user)
    _set_session_cookie(response, user["wallet"])
    return {"ok": True, "user": _user_view_with_state(user)}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
async def me(request: Request):
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    return {"user": _user_view_with_state(user)}


# ── Helper, используется в poll/admin для авторизации ────────────────────────

def current_user(request: Request) -> Optional[dict]:
    token  = request.cookies.get(COOKIE_NAME)
    wallet = auth_core.verify_session_token(token)
    if not wallet:
        return None
    return auth_core.find_user_by_wallet(wallet)
