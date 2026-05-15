"""
Связка зарегистрированных пользователей со студенческим реестром и whitelist'ом.

Регистрация (`auth.register`) сохраняет user в users.json, но кошелёк
ещё не появляется в Student-реестре, который используется в poll_service.
Здесь мы:
  - регистрируем кошелёк в Student-реестре с детерминированным secret из pk
    (так же как для keypair-участников);
  - на approve вызываем on-chain `addCommitment(...)` через whitelist_service.
"""
from __future__ import annotations

import hashlib
import logging

from app.core.auth import (
    get_users, find_user_by_wallet, mark_user_approved, user_public_view,
)
from app.core.zk import SNARK_FIELD, commitment_of
from app.models.student import (
    get_by_wallet, add_keypair_participant, Student, _registry,
)

logger = logging.getLogger("atomic-choice.users")


def _secret_from_private_key(private_key_hex: str) -> int:
    hex_str = private_key_hex.strip()
    if hex_str.startswith(("0x", "0X")):
        hex_str = hex_str[2:]
    raw = bytes.fromhex(hex_str)
    return int(hashlib.sha256(raw).hexdigest(), 16) % SNARK_FIELD


def sync_users_to_registry():
    """
    Гарантирует, что каждый зарегистрированный пользователь представлен
    в _registry student.py (для poll/whitelist логики).

    Безопасно вызывать многократно: уже зарегистрированных пропускает.
    Если пользователь уже approved (в users.json) — выставляем флаг
    whitelisted=True локально; реальное добавление в on-chain whitelist
    делается админом из UI или произошло раньше.
    """
    added = 0
    for u in get_users():
        existing = get_by_wallet(u["wallet"])
        if existing is None:
            # Регистрируем как «keypair-style» участника, но с именем = nick.
            s = Student(
                wallet=u["wallet"],
                name=u["nick"],
                group="registered",
                secret=_secret_from_private_key(u["private_key"]),
                commitment=int(u["commitment"]),
                whitelisted=bool(u.get("approved", False)),
            )
            _registry[u["wallet"].lower()] = s
            added += 1
        else:
            # Подровнять флаг
            if u.get("approved") and not existing.whitelisted:
                existing.whitelisted = True
    if added:
        logger.info("Synced %d registered users into Student-registry", added)


def register_user_in_registry(user: dict) -> Student:
    """Сразу при регистрации добавить пользователя в Student-реестр."""
    existing = get_by_wallet(user["wallet"])
    if existing:
        return existing
    s = Student(
        wallet=user["wallet"],
        name=user["nick"],
        group="registered",
        secret=_secret_from_private_key(user["private_key"]),
        commitment=int(user["commitment"]),
        whitelisted=False,
    )
    _registry[user["wallet"].lower()] = s
    return s


async def approve_user(wallet: str) -> dict:
    """
    Админ одобряет регистрацию → пользователь добавляется в on-chain whitelist.
    """
    from app.services.whitelist_service import add_student_to_whitelist

    user = find_user_by_wallet(wallet)
    if not user:
        raise ValueError(f"Пользователь {wallet} не найден")

    # Убедиться, что он в Student-реестре
    student = get_by_wallet(wallet)
    if student is None:
        student = register_user_in_registry(user)

    if student.whitelisted and user.get("approved"):
        return {"ok": True, "skipped": "already approved", "user": user_public_view(user)}

    result = await add_student_to_whitelist(wallet)
    mark_user_approved(wallet)
    return {"ok": True, "user": user_public_view(user), **result}


def pending_users() -> list[dict]:
    return [user_public_view(u) for u in get_users() if not u.get("approved")]


def approved_users() -> list[dict]:
    return [user_public_view(u) for u in get_users() if u.get("approved")]
