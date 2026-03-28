"""
Whitelist service.
Manages adding students to the on-chain Whitelist contract
and keeps the off-chain Merkle tree in sync.
"""
import logging
from web3 import Web3

from app.core.blockchain import get_whitelist_contract, send_tx, get_deployer_account
from app.core.merkle import get_tree, rebuild_tree_from_events
from app.models.student import get_all, get_by_wallet, mark_whitelisted, Student
from app.core.config import settings

logger = logging.getLogger("atomic-choice.whitelist")


async def get_whitelist_info() -> dict:
    contract = get_whitelist_contract()
    root  = contract.functions.root().call()
    size  = contract.functions.size().call()
    depth = contract.functions.depth().call()
    return {
        "root":  str(root),
        "root_hex": hex(root),
        "size":  size,
        "depth": depth,
    }


async def add_student_to_whitelist(wallet: str) -> dict:
    """
    Adds a student's identity commitment to the on-chain Whitelist.
    Returns tx receipt info.
    """
    student = get_by_wallet(wallet)
    if not student:
        raise ValueError(f"Student not found: {wallet}")
    if student.whitelisted:
        raise ValueError(f"Student already whitelisted: {wallet}")

    contract  = get_whitelist_contract()
    account   = get_deployer_account()

    commitment = student.commitment
    logger.info(
        "Adding commitment to whitelist | wallet=%s name=%s commitment=%s",
        student.wallet_short, student.name, hex(commitment)
    )

    fn = contract.functions.addCommitment(commitment)
    receipt = send_tx(fn, account.address, settings.DEPLOYER_PRIVATE_KEY)

    if receipt["status"] != 1:
        raise RuntimeError("Transaction reverted")

    # Sync off-chain tree
    get_tree().insert(commitment)
    mark_whitelisted(wallet)

    new_root = contract.functions.root().call()
    size     = contract.functions.size().call()

    logger.info(
        "✓ Commitment added | student=%s | new_root=%s | tree_size=%d",
        student.name, hex(new_root), size
    )

    return {
        "tx_hash":    receipt["transactionHash"].hex(),
        "block":      receipt["blockNumber"],
        "gas_used":   receipt["gasUsed"],
        "commitment": hex(commitment),
        "new_root":   str(new_root),
        "tree_size":  size,
    }


async def add_all_students_to_whitelist() -> list[dict]:
    """Batch-adds all seed students. Called during demo setup."""
    results = []
    for student in get_all():
        if not student.whitelisted:
            try:
                result = await add_student_to_whitelist(student.wallet)
                results.append({"student": student.name, "ok": True, **result})
            except Exception as e:
                logger.error("Failed to add %s: %s", student.name, e)
                results.append({"student": student.name, "ok": False, "error": str(e)})
    return results


async def sync_tree_from_chain():
    """
    Re-reads CommitmentAdded events and rebuilds the off-chain Merkle tree.
    Called on startup if contracts are already deployed.
    """
    contract = get_whitelist_contract()
    events   = contract.events.CommitmentAdded().get_logs(from_block=0)
    events   = sorted(events, key=lambda e: e["args"]["leafIndex"])
    commitments = [int(e["args"]["commitment"]) for e in events]

    rebuild_tree_from_events(commitments)

    # Mark whitelisted students
    for e in events:
        c = int(e["args"]["commitment"])
        for student in get_all():
            if student.commitment == c:
                student.whitelisted = True

    logger.info("Tree synced from chain: %d commitments", len(commitments))


def get_merkle_proof_for_wallet(wallet: str) -> dict:
    student = get_by_wallet(wallet)
    if not student:
        raise ValueError("Student not found")
    if not student.whitelisted:
        raise ValueError("Student not in whitelist yet")

    tree  = get_tree()
    idx   = tree.index_of(student.commitment)
    if idx == -1:
        raise ValueError("Commitment not in local tree — re-sync required")

    proof = tree.proof(idx)
    return {
        "commitment":   str(student.commitment),
        "leaf_index":   idx,
        "path_elements": [str(x) for x in proof["path_elements"]],
        "path_indices": proof["path_indices"],
        "root":         str(proof["root"]),
    }
