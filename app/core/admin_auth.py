"""
Простая защита /api/admin/* по заголовку X-Admin-Token.

Токен:
  1. settings.ADMIN_TOKEN из .env (если задан) — используется в production-демо;
  2. иначе генерируется случайный при старте и пишется в admin_token.txt
     + логируется в консоль. Файл попадает в .gitignore.
"""
from __future__ import annotations

import logging
import secrets
from pathlib import Path

from fastapi import Header, HTTPException, status

from app.core.config import settings

logger = logging.getLogger("atomic-choice.admin_auth")

_ADMIN_TOKEN_FILE = Path("admin_token.txt")
_token: str | None = None


def initialize_admin_token() -> str:
    """Вызывается на старте приложения. Возвращает финальный токен."""
    global _token
    if settings.ADMIN_TOKEN:
        _token = settings.ADMIN_TOKEN.strip()
        logger.info("Admin token loaded from .env")
        return _token

    if _ADMIN_TOKEN_FILE.exists():
        existing = _ADMIN_TOKEN_FILE.read_text(encoding="utf-8").strip()
        if existing:
            _token = existing
            logger.info(
                "Admin token loaded from %s (см. файл — раздавать только админу!)",
                _ADMIN_TOKEN_FILE,
            )
            return _token

    _token = secrets.token_urlsafe(24)
    _ADMIN_TOKEN_FILE.write_text(_token, encoding="utf-8")
    logger.info("━" * 60)
    logger.info(" ADMIN TOKEN сгенерирован и сохранён в %s", _ADMIN_TOKEN_FILE)
    logger.info(" Введите его в админ-панели браузера:")
    logger.info("     %s", _token)
    logger.info("━" * 60)
    return _token


def get_admin_token() -> str:
    if _token is None:
        return initialize_admin_token()
    return _token


def require_admin(x_admin_token: str | None = Header(default=None)):
    """FastAPI-зависимость: проверяет заголовок X-Admin-Token."""
    expected = get_admin_token()
    if not x_admin_token or x_admin_token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется корректный X-Admin-Token",
        )
    return True
