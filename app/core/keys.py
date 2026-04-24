"""
Key management for Atomic Choice.

На старте генерирует 10 Ethereum-keypair (или загружает существующие из файла).
Приватные ключи записываются в keys.txt (раздать участникам).
Публичные адреса (commitments) добавляются в вайтлист автоматически.

Логика:
  - keys.json  — машиночитаемое хранилище (wallet → {private_key, secret, commitment})
  - keys.txt   — человекочитаемое распределение (раздать участникам)

ВАЖНО: В production приватный ключ никогда не должен покидать устройство пользователя.
Здесь сервер хранит ключи только потому что он же и подписывает транзакции (demo-режим).
"""

import json
import logging
import secrets
from pathlib import Path

from eth_account import Account
from web3 import Web3

from app.core.zk import commitment_of, student_secret, SNARK_FIELD

logger = logging.getLogger("atomic-choice.keys")

KEYS_JSON = Path("keys.json")
KEYS_TXT  = Path("keys.txt")

NUM_KEYS  = 10


# ── Data structure ────────────────────────────────────────────────────────────

def _generate_keypair(index: int) -> dict:
    """
    Генерирует один Ethereum keypair.
    secret для ZK = sha256(private_key_bytes) % SNARK_FIELD.
    """
    acct = Account.create()
    private_key = acct.key.hex()          # "0x..."
    wallet      = acct.address            # checksum address

    # ZK identity: детерминированно из private_key
    import hashlib
    raw    = bytes.fromhex(private_key[2:])
    secret = int(hashlib.sha256(raw).hexdigest(), 16) % SNARK_FIELD
    comm   = commitment_of(secret)

    return {
        "index":       index,
        "wallet":      wallet,
        "private_key": private_key,
        "secret":      str(secret),         # ZK identity secret
        "commitment":  str(comm),           # = Poseidon(secret) — в вайтлист
    }


# ── Persistence ───────────────────────────────────────────────────────────────

def load_or_generate_keys() -> list[dict]:
    """
    Если keys.json существует — загружает.
    Иначе генерирует NUM_KEYS новых keypair, сохраняет JSON + TXT.
    """
    if KEYS_JSON.exists():
        data = json.loads(KEYS_JSON.read_text())
        logger.info("Loaded %d existing keypairs from %s", len(data), KEYS_JSON)
        return data

    logger.info("Generating %d fresh keypairs...", NUM_KEYS)
    pairs = [_generate_keypair(i) for i in range(NUM_KEYS)]

    # Save machine-readable JSON
    KEYS_JSON.write_text(json.dumps(pairs, indent=2, ensure_ascii=False))
    logger.info("Saved keypairs to %s", KEYS_JSON)

    # Save human-readable TXT for distribution
    _write_keys_txt(pairs)
    logger.info("Saved private keys to %s (distribute to voters)", KEYS_TXT)

    return pairs


def _write_keys_txt(pairs: list[dict]):
    lines = [
        "=" * 60,
        "  ATOMIC CHOICE — Ключи участников",
        "  Каждый участник получает ОДНУ строку.",
        "  Приватный ключ = ваша личность. Никому не передавайте!",
        "=" * 60,
        "",
    ]
    for p in pairs:
        lines += [
            f"Участник #{p['index'] + 1}",
            f"  Адрес (публичный):  {p['wallet']}",
            f"  Приватный ключ:     {p['private_key']}",
            "",
        ]
    lines += [
        "=" * 60,
        "  Для голосования войдите на платформу и введите",
        "  свой адрес (публичный ключ).",
        "=" * 60,
    ]
    KEYS_TXT.write_text("\n".join(lines), encoding="utf-8")


# ── Registry ──────────────────────────────────────────────────────────────────

_keypairs: list[dict] = []


def get_keypairs() -> list[dict]:
    return _keypairs


def get_keypair_by_wallet(wallet: str) -> dict | None:
    w = wallet.lower()
    return next((k for k in _keypairs if k["wallet"].lower() == w), None)


def initialize_keys() -> list[dict]:
    """Called once on startup."""
    global _keypairs
    _keypairs = load_or_generate_keys()
    return _keypairs
