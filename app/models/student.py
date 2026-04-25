"""
In-memory student/participant registry.

Поддерживает два источника участников:
  1. Seed-студенты (как было) — для demo
  2. Сгенерированные keypairs — для реального использования

secret хранится на сервере только в demo-режиме;
в production он никогда не покидает браузер пользователя.
"""
from dataclasses import dataclass, field
from app.core.zk import student_secret, commitment_of
import hashlib
import logging

logger = logging.getLogger("atomic-choice.students")

SNARK_FIELD = (
    21888242871839275222246405745257275088548364400416034343698204186575808495617
)


@dataclass
class Student:
    wallet: str          # checksummed
    name: str
    group: str
    secret: int          # ZK identity secret (demo: stored server-side)
    commitment: int      # = poseidon1(secret)
    whitelisted: bool = False          # глобальный вайтлист

    # per-poll whitelist: poll_address.lower() → bool
    poll_whitelisted: dict = field(default_factory=dict)

    @property
    def wallet_short(self) -> str:
        return self.wallet[:6] + "…" + self.wallet[-4:]

    @property
    def commitment_hex(self) -> str:
        return hex(self.commitment)

    def is_whitelisted_for_poll(self, poll_address: str) -> bool:
        """True если участник в глобальном вайтлисте ИЛИ в вайтлисте конкретного голосования."""
        return self.whitelisted or self.poll_whitelisted.get(poll_address.lower(), False)


# ── Seed test students ────────────────────────────────────────────────────────

_SEED = [
    ("0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266", "Алексей Петров",    "ИТ-31"),
    ("0x70997970C51812dc3A010C7d01b50e0d17dc79C8", "Мария Сидорова",    "ИТ-31"),
    ("0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC", "Дмитрий Козлов",    "ИТ-32"),
    ("0x90F79bf6EB2c4f870365E785982E1f101E93b906", "Анна Новикова",     "ИТ-32"),
    ("0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65", "Иван Морозов",      "ИТ-33"),
    ("0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc", "Екатерина Волкова", "ИТ-33"),
    ("0x976EA74026E726554dB657fA54763abd0C3a0aa9", "Сергей Лебедев",   "ИТ-34"),
    ("0x14dC79964da2C08b23698B3D3cc7Ca32193d9955", "Ольга Соколова",   "ИТ-34"),
]


def _secret_from_private_key(private_key_hex: str) -> int:
    """Детерминированный ZK-секрет из приватного ключа (для keypair участников)."""
    hex_str = private_key_hex.strip()
    if hex_str.startswith(("0x", "0X")):
        hex_str = hex_str[2:]
    raw = bytes.fromhex(hex_str)
    return int(hashlib.sha256(raw).hexdigest(), 16) % SNARK_FIELD


def _make_seed_students() -> dict[str, "Student"]:
    result = {}
    for wallet, name, group in _SEED:
        sec = student_secret(wallet)
        result[wallet.lower()] = Student(
            wallet=wallet,
            name=name,
            group=group,
            secret=sec,
            commitment=commitment_of(sec),
        )
    return result


# Singleton registry
_registry: dict[str, "Student"] = _make_seed_students()


# ── Public API ────────────────────────────────────────────────────────────────

def get_all() -> list["Student"]:
    return list(_registry.values())


def get_by_wallet(wallet: str) -> "Student | None":
    return _registry.get(wallet.lower())


def add_student(wallet: str, name: str, group: str) -> "Student":
    sec = student_secret(wallet)
    s = Student(
        wallet=wallet,
        name=name,
        group=group,
        secret=sec,
        commitment=commitment_of(sec),
    )
    _registry[wallet.lower()] = s
    return s


def add_keypair_participant(wallet: str, private_key: str, index: int) -> "Student":
    """
    Регистрирует участника из сгенерированного keypair.
    secret вычисляется из приватного ключа детерминированно.
    """
    sec  = _secret_from_private_key(private_key)
    comm = commitment_of(sec)
    s = Student(
        wallet=wallet,
        name=f"Участник #{index + 1}",
        group="keypair",
        secret=sec,
        commitment=comm,
    )
    _registry[wallet.lower()] = s
    logger.debug("Registered keypair participant: %s", wallet[:10] + "…")
    return s


def mark_whitelisted(wallet: str):
    s = _registry.get(wallet.lower())
    if s:
        s.whitelisted = True


def mark_whitelisted_for_poll(wallet: str, poll_address: str):
    """Добавляет участника в вайтлист конкретного голосования."""
    s = _registry.get(wallet.lower())
    if s:
        s.poll_whitelisted[poll_address.lower()] = True
        logger.debug("Whitelisted %s for poll %s", wallet[:10] + "…", poll_address[:10] + "…")
