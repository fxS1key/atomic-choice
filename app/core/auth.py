"""
Авторизация Atomic Choice.

Пользователь придумывает ник + пароль. Сервер выводит из них приватный
ключ через KDF и сохраняет ТОЛЬКО приватный ключ (для подписи демо-
транзакций) + публичный адрес + commitment + ник. Сам пароль никогда
не попадает на диск — KDF одностороння, и при логине пользователь
вводит пароль заново.

KDF:
    seed   = scrypt(password.utf8, salt=server_salt || nick.lower(), N=2**14)
    pk     = seed[:32]              # 32 байта приватного ключа Ethereum
    secret = sha256(pk) % SNARK_FIELD

Хранение  →  users.json (poll-whitelist-style):
    {
        "users": [
            {
                "nick":         "anastasiya",
                "wallet":       "0x...",
                "private_key":  "0x...",
                "commitment":   "1234...",
                "registered_at": 1715800000,
                "approved":     false
            }
        ]
    }

Сессии: HMAC-токен в куке `ac_session`, payload = wallet + expiry.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
import time
from pathlib import Path
from typing import Optional

from eth_account import Account

from app.core.zk import SNARK_FIELD

logger = logging.getLogger("atomic-choice.auth")

USERS_FILE   = Path("users.json")
SALT_FILE    = Path("server_salt.bin")     # тот же salt, что и в zk.py
SESSION_KEY_FILE = Path("session_key.bin")
SESSION_TTL  = 7 * 24 * 3600                # неделя

NICK_RE      = re.compile(r"^[a-zA-Z0-9_\-\.]{3,32}$")
PASSWORD_MIN = 6
SCRYPT_N     = 2 ** 14                       # ~16 МБ памяти, ~50 мс CPU


# ── Server-side keys ──────────────────────────────────────────────────────────

def _load_or_create(path: Path, size: int) -> bytes:
    if path.exists():
        data = path.read_bytes()
        if len(data) == size:
            return data
    data = secrets.token_bytes(size)
    path.write_bytes(data)
    return data


_SERVER_SALT = _load_or_create(SALT_FILE, 32)
_SESSION_KEY = _load_or_create(SESSION_KEY_FILE, 32)


# ── KDF: nick + password → ethereum private key ───────────────────────────────

def _derive_private_key(nick: str, password: str) -> str:
    """
    Детерминированно выводит приватный ключ Ethereum из (nick, password).
    Salt — серверный + ник (защита от радужных таблиц). N=2**14 — щадящий,
    чтобы регистрация занимала <200 мс.
    """
    salt = _SERVER_SALT + nick.lower().encode("utf-8")
    seed = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N, r=8, p=1,
        dklen=32,
    )
    # eth-секрет должен попадать в curve order; scrypt-выход почти всегда ок,
    # но если случайно получится 0 — берём sha256.
    if int.from_bytes(seed, "big") == 0:
        seed = hashlib.sha256(seed).digest()
    return "0x" + seed.hex()


def derive_wallet_from_credentials(nick: str, password: str) -> dict:
    """
    Возвращает {wallet, private_key, commitment, secret} для пары (nick, password).
    Ничего не сохраняет на диск.
    """
    pk = _derive_private_key(nick, password)
    acct = Account.from_key(pk)

    raw    = bytes.fromhex(pk[2:])
    secret = int(hashlib.sha256(raw).hexdigest(), 16) % SNARK_FIELD
    commit = _commitment_from_secret(secret)
    return {
        "wallet":      acct.address,
        "private_key": pk,
        "secret":      secret,
        "commitment":  commit,
    }


def _commitment_from_secret(secret: int) -> int:
    # Импорт здесь — чтобы избежать циклической зависимости с zk.py при загрузке.
    from app.core.zk import commitment_of
    return commitment_of(secret)


# ── Users persistence ─────────────────────────────────────────────────────────

_users_cache: list[dict] = []


def _load_users() -> list[dict]:
    if not USERS_FILE.exists():
        return []
    try:
        data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
        return list(data.get("users", []))
    except Exception as e:
        logger.warning("Не удалось загрузить %s: %s", USERS_FILE, e)
        return []


def _save_users():
    try:
        USERS_FILE.write_text(
            json.dumps({"users": _users_cache}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logger.error("Не удалось сохранить %s: %s", USERS_FILE, e)


def initialize_users():
    """Вызывается на старте приложения."""
    global _users_cache
    _users_cache = _load_users()
    logger.info("Loaded %d registered users from %s", len(_users_cache), USERS_FILE)


def get_users() -> list[dict]:
    return list(_users_cache)


def find_user_by_nick(nick: str) -> Optional[dict]:
    n = nick.lower()
    return next((u for u in _users_cache if u["nick"].lower() == n), None)


def find_user_by_wallet(wallet: str) -> Optional[dict]:
    w = wallet.lower()
    return next((u for u in _users_cache if u["wallet"].lower() == w), None)


def mark_user_approved(wallet: str):
    u = find_user_by_wallet(wallet)
    if u:
        u["approved"] = True
        _save_users()


# ── Register / login ──────────────────────────────────────────────────────────

class AuthError(Exception):
    pass


def validate_nick(nick: str):
    if not NICK_RE.match(nick):
        raise AuthError(
            "Ник должен быть 3–32 символа: латиница, цифры, «_», «-», «.»."
        )


def validate_password(password: str):
    if len(password) < PASSWORD_MIN:
        raise AuthError(f"Пароль должен быть минимум {PASSWORD_MIN} символов.")


def register(nick: str, password: str) -> dict:
    """
    Регистрирует нового пользователя.
    Если nick занят И deriv-pk совпадает → возвращает существующего (re-login).
    Если nick занят И pk не совпадает → ошибка.
    """
    nick = nick.strip()
    validate_nick(nick)
    validate_password(password)

    derived = derive_wallet_from_credentials(nick, password)

    existing = find_user_by_nick(nick)
    if existing:
        # Тот же пароль → молча возвращаем существующего пользователя
        if existing["wallet"].lower() == derived["wallet"].lower():
            return existing
        raise AuthError(
            "Ник уже занят. Выберите другой или войдите с правильным паролем."
        )

    user = {
        "nick":          nick,
        "wallet":        derived["wallet"],
        "private_key":   derived["private_key"],
        "commitment":    str(derived["commitment"]),
        "registered_at": int(time.time()),
        "approved":      False,           # whitelist решает админ
    }
    _users_cache.append(user)
    _save_users()

    logger.info("✓ Registered user nick=%r wallet=%s", nick, derived["wallet"])
    return user


def login(nick: str, password: str) -> dict:
    """
    Логин по (nick, password): пересчитываем pk и сверяем с сохранённым.
    Возвращаем user-объект, если совпало.
    """
    nick = nick.strip()
    validate_nick(nick)
    validate_password(password)

    user = find_user_by_nick(nick)
    if not user:
        raise AuthError("Пользователь не найден. Сначала зарегистрируйтесь.")

    derived = derive_wallet_from_credentials(nick, password)
    if derived["wallet"].lower() != user["wallet"].lower():
        raise AuthError("Неверный пароль.")

    return user


# ── Session token (HMAC, без зависимостей) ────────────────────────────────────

def issue_session_token(wallet: str) -> str:
    payload = json.dumps(
        {"wallet": wallet.lower(), "exp": int(time.time()) + SESSION_TTL},
        separators=(",", ":"),
    ).encode("utf-8")
    sig = hmac.new(_SESSION_KEY, payload, hashlib.sha256).digest()
    return (
        base64.urlsafe_b64encode(payload).decode().rstrip("=")
        + "."
        + base64.urlsafe_b64encode(sig).decode().rstrip("=")
    )


def verify_session_token(token: Optional[str]) -> Optional[str]:
    """Возвращает wallet, если токен валиден; иначе None."""
    if not token or "." not in token:
        return None
    try:
        payload_b64, sig_b64 = token.split(".", 1)
        pad = "=" * ((4 - len(payload_b64) % 4) % 4)
        payload = base64.urlsafe_b64decode(payload_b64 + pad)
        pad = "=" * ((4 - len(sig_b64) % 4) % 4)
        sig = base64.urlsafe_b64decode(sig_b64 + pad)
        expected = hmac.new(_SESSION_KEY, payload, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, sig):
            return None
        data = json.loads(payload)
        if int(data.get("exp", 0)) < int(time.time()):
            return None
        return data["wallet"]
    except Exception:
        return None


# ── Public API helper ─────────────────────────────────────────────────────────

def user_public_view(u: dict) -> dict:
    """То, что безопасно отдавать в API (без приватного ключа)."""
    return {
        "nick":          u["nick"],
        "wallet":        u["wallet"],
        "commitment":    u["commitment"],
        "approved":      u.get("approved", False),
        "registered_at": u.get("registered_at"),
    }
