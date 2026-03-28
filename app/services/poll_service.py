"""
Poll service.
Creates polls via VotingFactory and reads poll data from VotingPoll contracts.
"""
import logging
import time
from web3 import Web3

from app.core.blockchain import (
    get_factory_contract, get_poll_contract, send_tx,
    get_deployer_account, get_w3, sync_chain_time,
)
from app.core.config import settings
from app.core.zk import nullifier_of, make_stub_proof
from app.core.merkle import get_tree
from app.models.student import get_by_wallet
from app.services.whitelist_service import get_merkle_proof_for_wallet

logger = logging.getLogger("atomic-choice.polls")

OPTION_LABELS = ["А", "Б", "В", "Г", "Д", "Е", "Ж", "З", "И", "К",
                 "Л", "М", "Н", "О", "П", "Р"]

# ── Seed poll definitions ────────────────────────────────────────────────────

SEED_POLLS = [
    {
        "title": "Выборы старосты группы ИТ-31",
        "description": "Ежегодные выборы старосты. Выберите кандидата на следующий учебный год.",
        "options": ["Алексей Петров", "Мария Сидорова", "Дмитрий Козлов"],
        "start_offset": 60,
        "duration": 86400,
    },
    {
        "title": "Лучший преподаватель семестра",
        "description": "Оцените преподавателей и выберите лучшего по итогам семестра.",
        "options": ["Проф. Иванов А.В.", "Доц. Смирнова К.Б.", "Ст. преп. Фёдоров П.Н.", "Проф. Белова Е.С."],
        "start_offset": 60,
        "duration": 172800,
    },
    {
        "title": "Язык программирования в обязательную программу",
        "description": "Какой язык добавить в учебный план следующего года?",
        "options": ["Rust", "Go", "Kotlin", "Swift"],
        "start_offset": 60,
        "duration": 43200,
    },
]


# ── Poll CRUD ─────────────────────────────────────────────────────────────────

async def create_poll(
    title: str,
    description: str,
    options: list[str],
    start_offset_seconds: int = 60,
    duration_seconds: int = 86400,
) -> dict:
    factory = get_factory_contract()
    account = get_deployer_account()
    sync_chain_time()
    now       = int(time.time())
    start     = now + start_offset_seconds
    end     = start + duration_seconds

    logger.info(
        "Creating poll | title=%r | options=%d | start=%d | end=%d",
        title, len(options), start, end
    )

    # Store option labels in description as JSON suffix
    # (the contract stores only count; labels live in description)
    import json
    desc_full = json.dumps({
        "text": description,
        "options": options,
    })

    fn = factory.functions.createPoll(
        title,
        desc_full,
        len(options),
        start,
        end,
    )
    receipt = send_tx(fn, account.address, settings.DEPLOYER_PRIVATE_KEY)

    if receipt["status"] != 1:
        raise RuntimeError("createPoll transaction reverted")

    # Get poll address from PollCreated event
    factory_contract = get_factory_contract()
    logs = factory_contract.events.PollCreated().process_receipt(receipt)
    if not logs:
        raise RuntimeError("PollCreated event not found in receipt")

    event     = logs[0]
    poll_addr = event["args"]["pollAddress"]
    poll_id   = event["args"]["pollId"]

    logger.info(
        "✓ Poll created | id=%d | address=%s | tx=%s | block=%d",
        poll_id, poll_addr,
        receipt["transactionHash"].hex(),
        receipt["blockNumber"],
    )
    return {
        "poll_id":      poll_id,
        "poll_address": poll_addr,
        "tx_hash":      receipt["transactionHash"].hex(),
        "block":        receipt["blockNumber"],
        "gas_used":     receipt["gasUsed"],
    }


async def get_all_polls() -> list[dict]:
    factory = get_factory_contract()
    total   = factory.functions.totalPolls().call()
    if total == 0:
        return []

    addresses = factory.functions.getPolls(0, total).call()
    polls = []
    for addr in addresses:
        try:
            polls.append(await _read_poll(addr))
        except Exception as e:
            logger.warning("Failed to read poll %s: %s", addr, e)
    return polls


async def get_poll(address: str) -> dict:
    return await _read_poll(address)


async def cast_vote(poll_address: str, option_index: int, voter_wallet: str) -> dict:
    """
    Full voting flow:
    1. Load student identity
    2. Get Merkle proof
    3. Compute nullifier
    4. Build stub ZK proof
    5. Submit castVote() transaction
    """
    student = get_by_wallet(voter_wallet)
    if not student:
        raise ValueError("Wallet not in student registry")
    if not student.whitelisted:
        raise ValueError("Student not whitelisted — admin must add you first")

    poll_contract = get_poll_contract(poll_address)
    sync_chain_time()

    # Read poll metadata
    poll_id      = poll_contract.functions.pollId().call()
    start_time   = poll_contract.functions.startTime().call()
    end_time     = poll_contract.functions.endTime().call()
    options_count = poll_contract.functions.optionsCount().call()

    now = int(time.time())
    if now < start_time:
        raise ValueError("Poll has not started yet")
    if now > end_time:
        raise ValueError("Poll has ended")
    if option_index >= options_count:
        raise ValueError(f"Invalid option index {option_index}")

    # Compute nullifier
    nullifier = nullifier_of(student.secret, poll_id)

    # Check double-vote
    if poll_contract.functions.nullifierUsed(nullifier).call():
        raise ValueError("You have already voted in this poll (nullifier used)")

    # Get Merkle proof
    proof_data  = get_merkle_proof_for_wallet(voter_wallet)
    merkle_root = int(proof_data["root"])

    # Verify root is accepted by poll
    if not poll_contract.functions.validRoots(merkle_root).call():
        # Try current whitelist root
        from app.core.blockchain import get_whitelist_contract
        wl = get_whitelist_contract()
        current_root = wl.functions.root().call()
        if not poll_contract.functions.validRoots(current_root).call():
            raise ValueError(
                "Merkle root mismatch. "
                "The poll was created before you were whitelisted. "
                "Admin must call addWhitelistRoot() on the poll."
            )
        merkle_root = current_root

    # Build stub proof (VerifierStub accepts anything)
    zk = make_stub_proof(nullifier, merkle_root, option_index, poll_id)

    logger.info(
        "Casting vote | voter=%s (%s) | poll=%d | option=%d | nullifier=%s",
        student.name, student.wallet_short,
        poll_id, option_index,
        hex(nullifier)[:18] + "…"
    )

    fn = poll_contract.functions.castVote(
        nullifier,
        merkle_root,
        option_index,
        zk["pA"],
        zk["pB"],
        zk["pC"],
    )
    account = get_deployer_account()  # demo: server signs on behalf of voter
    receipt = send_tx(fn, account.address, settings.DEPLOYER_PRIVATE_KEY)

    if receipt["status"] != 1:
        raise RuntimeError("castVote transaction reverted")

    total_votes = poll_contract.functions.totalVotes().call()

    logger.info(
        "✓ Vote cast | voter=%s | poll=%d | option=%d | tx=%s | block=%d | total_votes=%d",
        student.name, poll_id, option_index,
        receipt["transactionHash"].hex(),
        receipt["blockNumber"],
        total_votes,
    )

    return {
        "ok":          True,
        "tx_hash":     receipt["transactionHash"].hex(),
        "block":       receipt["blockNumber"],
        "gas_used":    receipt["gasUsed"],
        "nullifier":   hex(nullifier),
        "merkle_root": str(merkle_root),
        "total_votes": total_votes,
        "message":     "✓ Голос анонимно засчитан в блокчейне",
    }


async def seed_polls() -> list[dict]:
    """Creates the demo seed polls. Called during setup."""
    results = []
    for p in SEED_POLLS:
        try:
            r = await create_poll(
                title=p["title"],
                description=p["description"],
                options=p["options"],
                start_offset_seconds=p["start_offset"],
                duration_seconds=p["duration"],
            )
            results.append({"title": p["title"], "ok": True, **r})
        except Exception as e:
            logger.error("Failed to create poll %r: %s", p["title"], e)
            results.append({"title": p["title"], "ok": False, "error": str(e)})
    return results


# ── Internal reader ───────────────────────────────────────────────────────────

async def _read_poll(address: str) -> dict:
    import json as _json
    contract = get_poll_contract(address)

    poll_id       = contract.functions.pollId().call()
    title         = contract.functions.title().call()
    raw_desc      = contract.functions.description().call()
    start_time    = contract.functions.startTime().call()
    end_time      = contract.functions.endTime().call()
    options_count = contract.functions.optionsCount().call()
    state         = contract.functions.state().call()
    total_votes   = contract.functions.totalVotes().call()
    is_active     = contract.functions.isActive().call()
    results       = contract.functions.getResults().call()

    # Parse options from description JSON
    options = []
    desc    = raw_desc
    try:
        parsed  = _json.loads(raw_desc)
        desc    = parsed.get("text", raw_desc)
        options = parsed.get("options", [])
    except Exception:
        options = [f"Вариант {i+1}" for i in range(options_count)]

    now = int(time.time())
    if state == 1:
        status = "ended"
    elif now < start_time:
        status = "upcoming"
    elif now <= end_time:
        status = "active"
    else:
        status = "ended"

    total = sum(results) or 1
    percentages = [round(v / total * 100) for v in results]

    return {
        "address":      address,
        "poll_id":      poll_id,
        "title":        title,
        "description":  desc,
        "options":      options,
        "start_time":   start_time,
        "end_time":     end_time,
        "options_count": options_count,
        "state":        state,
        "status":       status,
        "total_votes":  total_votes,
        "is_active":    is_active,
        "results":      [int(r) for r in results],
        "percentages":  percentages,
    }
