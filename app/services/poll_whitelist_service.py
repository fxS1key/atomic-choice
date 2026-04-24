"""
Per-poll whitelist service.

Позволяет создателю голосования добавлять участников в вайтлист
своего конкретного голосования (не глобальный).

Реализация:
  - Сервер ведёт off-chain Merkle tree для каждого голосования отдельно.
  - При добавлении участника → вызываем addWhitelistRoot() на контракте VotingPoll,
    обновляя корень дерева для этого голосования.
  - Участник сможет голосовать, даже если он не в глобальном вайтлисте.

Контроль доступа:
  - В demo-режиме нет подписи транзакции от создателя (всё от deployer).
  - Метаданные "кто создал" хранятся в _poll_creators (in-memory).
  - В production — проверка подписи создателя через EIP-712.
"""
import logging
from typing import Optional

from web3 import Web3

from app.core.blockchain import get_poll_contract, get_whitelist_contract, send_tx, get_deployer_account
from app.core.merkle import IncrementalMerkleTree, _hash_pair
from app.core.config import settings
from app.models.student import (
    get_by_wallet, mark_whitelisted_for_poll,
    add_keypair_participant, Student,
)
from app.core.zk import commitment_of

logger = logging.getLogger("atomic-choice.poll_whitelist")

# ── Per-poll state ────────────────────────────────────────────────────────────

# poll_address.lower() → IncrementalMerkleTree (off-chain)
_poll_trees: dict[str, IncrementalMerkleTree] = {}

# poll_address.lower() → creator_wallet.lower()
_poll_creators: dict[str, str] = {}

# poll_address.lower() → list of wallet strings (для отображения)
_poll_members: dict[str, list[str]] = {}


def register_poll_creator(poll_address: str, creator_wallet: str):
    """Вызывается при создании голосования, фиксирует создателя."""
    _poll_creators[poll_address.lower()] = creator_wallet.lower()
    _poll_trees[poll_address.lower()] = IncrementalMerkleTree(depth=10)
    _poll_members[poll_address.lower()] = []
    logger.info("Poll %s registered, creator=%s", poll_address[:10] + "…", creator_wallet[:10] + "…")


def get_poll_creator(poll_address: str) -> Optional[str]:
    return _poll_creators.get(poll_address.lower())


def get_poll_members(poll_address: str) -> list[str]:
    return _poll_members.get(poll_address.lower(), [])


def get_poll_tree(poll_address: str) -> Optional[IncrementalMerkleTree]:
    return _poll_trees.get(poll_address.lower())


async def add_wallet_to_poll_whitelist(
    poll_address: str,
    voter_wallet: str,
    requester_wallet: str,
) -> dict:
    """
    Добавляет voter_wallet в вайтлист голосования poll_address.

    requester_wallet — должен совпадать с создателем голосования.
    (В production проверяется подпись; здесь просто wallet-сравнение.)
    """
    poll_addr_lower = poll_address.lower()

    # ── Проверка прав ──────────────────────────────────────────────────────────
    creator = _poll_creators.get(poll_addr_lower)
    if creator is None:
        # Голосование не было создано через наш сервис — допускаем любого admin
        logger.warning(
            "Poll %s not registered locally; allowing deployer only",
            poll_address[:10] + "…"
        )
    elif requester_wallet.lower() != creator:
        raise PermissionError(
            f"Только создатель голосования может управлять его вайтлистом. "
            f"Ожидался: {creator[:10]}…, получен: {requester_wallet[:10]}…"
        )

    # ── Найти/создать участника ────────────────────────────────────────────────
    student = get_by_wallet(voter_wallet)
    if student is None:
        raise ValueError(
            f"Кошелёк {voter_wallet} не найден в реестре участников. "
            f"Сначала добавьте его через POST /api/admin/students или "
            f"убедитесь, что он был сгенерирован при старте."
        )

    # ── Off-chain дерево для этого голосования ────────────────────────────────
    if poll_addr_lower not in _poll_trees:
        _poll_trees[poll_addr_lower] = IncrementalMerkleTree(depth=10)
        _poll_members[poll_addr_lower] = []

    tree = _poll_trees[poll_addr_lower]
    commitment = student.commitment

    # Проверка дубликата
    if tree.index_of(commitment) != -1:
        raise ValueError(f"Участник {voter_wallet} уже в вайтлисте этого голосования")

    # Вставляем в дерево
    tree.insert(commitment)
    new_root = tree.root()

    # ── Обновляем корень в контракте VotingPoll ───────────────────────────────
    poll_contract = get_poll_contract(poll_address)
    account       = get_deployer_account()

    fn = poll_contract.functions.addWhitelistRoot(new_root)
    receipt = send_tx(fn, account.address, settings.DEPLOYER_PRIVATE_KEY)

    if receipt["status"] != 1:
        # Откат: убираем из дерева
        tree.leaves.pop()
        raise RuntimeError("addWhitelistRoot транзакция reverted")

    # Пометить участника как вайтлистнутого для этого голосования
    mark_whitelisted_for_poll(voter_wallet, poll_address)
    _poll_members[poll_addr_lower].append(voter_wallet)

    logger.info(
        "✓ Added %s to poll %s whitelist | new_root=%s | tree_size=%d",
        voter_wallet[:10] + "…",
        poll_address[:10] + "…",
        hex(new_root)[:14] + "…",
        len(tree.leaves),
    )

    return {
        "ok":          True,
        "voter":       voter_wallet,
        "poll":        poll_address,
        "commitment":  hex(commitment),
        "new_root":    str(new_root),
        "tree_size":   len(tree.leaves),
        "tx_hash":     receipt["transactionHash"].hex(),
        "block":       receipt["blockNumber"],
        "gas_used":    receipt["gasUsed"],
    }


def get_poll_merkle_proof(poll_address: str, voter_wallet: str) -> dict:
    """
    Возвращает Merkle proof участника из per-poll дерева.
    Если участника нет в per-poll дереве — пробует глобальный.
    """
    from app.services.whitelist_service import get_merkle_proof_for_wallet
    from app.core.merkle import get_tree

    student = get_by_wallet(voter_wallet)
    if not student:
        raise ValueError("Участник не найден")

    tree = _poll_trees.get(poll_address.lower())
    if tree:
        idx = tree.index_of(student.commitment)
        if idx != -1:
            proof = tree.proof(idx)
            return {
                "source":        "poll_whitelist",
                "commitment":    str(student.commitment),
                "leaf_index":    idx,
                "path_elements": [str(x) for x in proof["path_elements"]],
                "path_indices":  proof["path_indices"],
                "root":          str(proof["root"]),
            }

    # Fallback: глобальный вайтлист
    if student.whitelisted:
        return {**get_merkle_proof_for_wallet(voter_wallet), "source": "global_whitelist"}

    raise ValueError(
        f"Участник {voter_wallet} не в вайтлисте этого голосования и не в глобальном вайтлисте"
    )
