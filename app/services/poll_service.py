"""
Poll service.
Creates polls via VotingFactory and reads poll data from VotingPoll contracts.

Изменения:
  - Результаты скрыты (возвращаются нули) пока голосование активно.
    Это решает проблему анонимности: никто не может отслеживать
    динамику голосования в реальном времени.
  - castVote использует per-poll whitelist если участник там есть.
  - Регистрация создателя голосования при создании.
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


# ── Vote-authorization message ────────────────────────────────────────────────
# Канонический формат сообщения, которое голосующий подписывает в браузере.
# Формат фиксирован, чтобы бэкенд мог точно восстановить и сравнить сообщение.

def build_vote_message(poll_address: str, option_index: int, nonce: str) -> str:
    return (
        "Atomic Choice — confirm vote\n"
        f"poll: {poll_address.lower()}\n"
        f"option: {option_index}\n"
        f"nonce: {nonce}"
    )


# ── Anti-replay nonce storage ────────────────────────────────────────────────
# In-memory: (poll_lower, wallet_lower, nonce) → True
_used_nonces: set[tuple[str, str, str]] = set()


def _is_nonce_used(poll_address: str, wallet: str, nonce: str) -> bool:
    key = (poll_address.lower(), wallet.lower(), nonce)
    if key in _used_nonces:
        return True
    _used_nonces.add(key)
    return False

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
    creator_wallet: str | None = None,
) -> dict:
    factory = get_factory_contract()
    account = get_deployer_account()
    sync_chain_time()
    now   = int(time.time())
    start = now + start_offset_seconds
    end   = start + duration_seconds

    logger.info(
        "Creating poll | title=%r | options=%d | start=%d | end=%d",
        title, len(options), start, end
    )

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

    factory_contract = get_factory_contract()
    logs = factory_contract.events.PollCreated().process_receipt(receipt)
    if not logs:
        raise RuntimeError("PollCreated event not found in receipt")

    event     = logs[0]
    poll_addr = event["args"]["pollAddress"]
    poll_id   = event["args"]["pollId"]

    # Регистрируем создателя голосования для per-poll whitelist
    from app.services.poll_whitelist_service import register_poll_creator
    effective_creator = creator_wallet or account.address
    register_poll_creator(poll_addr, effective_creator)

    logger.info(
        "✓ Poll created | id=%d | address=%s | creator=%s | tx=%s | block=%d",
        poll_id, poll_addr, effective_creator[:10] + "…",
        receipt["transactionHash"].hex(),
        receipt["blockNumber"],
    )
    return {
        "poll_id":      poll_id,
        "poll_address": poll_addr,
        "creator":      effective_creator,
        "tx_hash":      receipt["transactionHash"].hex(),
        "block":        receipt["blockNumber"],
        "gas_used":     receipt["gasUsed"],
    }


async def get_all_polls(reveal_results: bool = False) -> list[dict]:
    factory = get_factory_contract()
    total   = factory.functions.totalPolls().call()
    if total == 0:
        return []

    addresses = factory.functions.getPolls(0, total).call()
    polls = []
    for addr in addresses:
        try:
            polls.append(await _read_poll(addr, reveal_results=reveal_results))
        except Exception as e:
            logger.warning("Failed to read poll %s: %s", addr, e)
    return polls


async def get_poll(address: str, reveal_results: bool = False) -> dict:
    return await _read_poll(address, reveal_results=reveal_results)


async def cast_vote(
    poll_address: str,
    option_index: int,
    voter_wallet: str,
    signature: str,
    message: str,
    nonce: str,
) -> dict:
    """
    Full voting flow:
    1. Verify EIP-191 signature → recover signer wallet (proof-of-private-key)
    2. Load student identity
    3. Check per-poll whitelist (or global)
    4. Get Merkle proof
    5. Compute nullifier
    6. Build stub ZK proof
    7. Submit castVote() via deployer relay (preserves on-chain anonymity)

    Авторизация:
    - Голос подписывается приватным ключом голосующего (EIP-191 personal_sign).
    - Сервер восстанавливает адрес из подписи → подтверждает владение PK.
    - Только этот адрес используется для проверки вайтлиста (claim не доверяем).

    Анонимность:
    - msg.sender on-chain — deployer (не раскрывает личность голосующего).
    - В транзакции видно только nullifierHash.
    - Результаты скрыты до окончания голосования.
    """
    from eth_account.messages import encode_defunct
    from eth_account import Account

    expected_message = build_vote_message(poll_address, option_index, nonce)
    if message.strip() != expected_message:
        raise ValueError(
            "Подписанное сообщение не совпадает с ожидаемым. "
            "Голосование отклонено."
        )

    try:
        recovered = Account.recover_message(
            encode_defunct(text=message), signature=signature
        )
    except Exception as e:
        raise ValueError(f"Не удалось проверить подпись: {e}")

    if recovered.lower() != voter_wallet.lower():
        raise ValueError(
            "Подпись не соответствует указанному адресу. "
            "Голосуйте только своим приватным ключом."
        )

    # ── Anti-replay: тот же nonce нельзя использовать дважды для пары (poll, wallet)
    if _is_nonce_used(poll_address, voter_wallet, nonce):
        raise ValueError("Этот nonce уже использовался — повторите попытку.")

    student = get_by_wallet(voter_wallet)
    if not student:
        raise ValueError("Кошелёк не найден в реестре участников")

    # ── Membership check ──────────────────────────────────────────────────────
    # Если участник в per-poll whitelist — он голосует ТОЛЬКО в этом голосовании.
    # Если в глобальном — может голосовать в любом.
    in_poll_wl = student.is_whitelisted_for_poll(poll_address)
    in_global  = student.whitelisted

    if not in_poll_wl and not in_global:
        raise ValueError(
            "Вы не в вайтлисте этого голосования. "
            "Создатель должен добавить вас через POST /api/polls/{address}/whitelist."
        )

    poll_contract = get_poll_contract(poll_address)
    sync_chain_time()

    poll_id       = poll_contract.functions.pollId().call()
    start_time    = poll_contract.functions.startTime().call()
    end_time      = poll_contract.functions.endTime().call()
    options_count = poll_contract.functions.optionsCount().call()

    now = int(time.time())
    if now < start_time:
        raise ValueError("Голосование ещё не началось")
    if now > end_time:
        raise ValueError("Голосование уже завершено")
    if option_index >= options_count:
        raise ValueError(f"Недопустимый номер варианта: {option_index}")

    nullifier = nullifier_of(student.secret, poll_id)

    if poll_contract.functions.nullifierUsed(nullifier).call():
        raise ValueError("Вы уже участвовали в этом голосовании.")

    # Получаем Merkle proof: сначала per-poll, потом глобальный
    try:
        from app.services.poll_whitelist_service import get_poll_merkle_proof
        proof_data  = get_poll_merkle_proof(poll_address, voter_wallet)
        merkle_root = int(proof_data["root"])
    except ValueError:
        # Fallback: глобальный вайтлист
        proof_data  = get_merkle_proof_for_wallet(voter_wallet)
        merkle_root = int(proof_data["root"])

    # Проверяем что root принят контрактом голосования
    if not poll_contract.functions.validRoots(merkle_root).call():
        from app.core.blockchain import get_whitelist_contract
        wl = get_whitelist_contract()
        current_root = wl.functions.root().call()
        if poll_contract.functions.validRoots(current_root).call():
            # Глобальный корень уже зарегистрирован → используем его
            merkle_root = current_root
        else:
            # Пытаемся самостоятельно синхронизировать корень с контрактом —
            # это убирает «висячую» ошибку Merkle root не принят, когда сервер
            # перезапускался или контракт был передеплоен.
            try:
                from app.services.poll_whitelist_service import sync_poll_root
                await sync_poll_root(poll_address)  # без проверки права (внутренний вызов)
            except Exception as sync_err:
                logger.warning(
                    "Auto-sync of merkle root failed for poll %s: %s",
                    poll_address[:10] + "…", sync_err,
                )
                raise ValueError(
                    "Merkle root не принят контрактом. "
                    "Создатель голосования должен обновить корень вайтлиста: "
                    f"{sync_err}"
                )
            # После синка пересчитываем proof — корень мог сдвинуться
            try:
                from app.services.poll_whitelist_service import get_poll_merkle_proof
                proof_data  = get_poll_merkle_proof(poll_address, voter_wallet)
                merkle_root = int(proof_data["root"])
            except ValueError:
                proof_data  = get_merkle_proof_for_wallet(voter_wallet)
                merkle_root = int(proof_data["root"])
            if not poll_contract.functions.validRoots(merkle_root).call():
                raise ValueError(
                    "Merkle root всё ещё не принят контрактом даже после "
                    "автоматического обновления. Создатель должен вручную "
                    "вызвать «Обновить вайтлист»."
                )

    zk = make_stub_proof(nullifier, merkle_root, option_index, poll_id)

    # NB. Анонимность: не логируем option_index и личность голосующего
    # на уровне INFO. Только nullifier (псевдоним) и факт голосования.
    logger.info(
        "Casting anonymous vote | poll=%d | nullifier=%s",
        poll_id, hex(nullifier)[:18] + "…"
    )
    logger.debug(
        "[debug] voter=%s (%s) option=%d",
        student.name, student.wallet_short, option_index,
    )

    fn = poll_contract.functions.castVote(
        nullifier,
        merkle_root,
        option_index,
        zk["pA"],
        zk["pB"],
        zk["pC"],
    )
    # Транзакция всегда подписывается от deployer — личность голосующего скрыта
    account = get_deployer_account()
    receipt = send_tx(fn, account.address, settings.DEPLOYER_PRIVATE_KEY)

    if receipt["status"] != 1:
        raise RuntimeError("castVote transaction reverted")

    total_votes = poll_contract.functions.totalVotes().call()

    logger.info(
        "✓ Anonymous vote cast | poll=%d | tx=%s | block=%d | total_votes=%d",
        poll_id,
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
        "message":     "✓ Голос анонимно засчитан в блокчейне. Результаты будут открыты после завершения голосования.",
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

async def _read_poll(address: str, reveal_results: bool = False) -> dict:
    """
    Читает данные голосования из контракта.

    reveal_results=False (по умолчанию):
      Пока голосование активно — возвращает нули вместо реальных результатов.
      Это защищает от "бандвагон-эффекта" и сохраняет конфиденциальность.

    reveal_results=True:
      Полные данные. Используется только после endTime или по явному запросу.
    """
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
    raw_results   = contract.functions.getResults().call()

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

    # ── Скрываем результаты пока голосование активно ──────────────────────────
    results_hidden = (status == "active") and not reveal_results
    if results_hidden:
        results     = [0] * options_count
        percentages = [0] * options_count
    else:
        results = [int(r) for r in raw_results]
        total   = sum(results) or 1
        percentages = [round(v / total * 100) for v in results]

    # Создатель голосования (из per-poll registry)
    from app.services.poll_whitelist_service import (
        get_poll_creator, get_poll_members
    )
    creator = get_poll_creator(address)
    members = get_poll_members(address)

    return {
        "address":        address,
        "poll_id":        poll_id,
        "title":          title,
        "description":    desc,
        "options":        options,
        "start_time":     start_time,
        "end_time":       end_time,
        "options_count":  options_count,
        "state":          state,
        "status":         status,
        "total_votes":    total_votes,
        "is_active":      is_active,
        "results":        results,
        "percentages":    percentages,
        "results_hidden": results_hidden,
        "creator":        creator,
        "poll_whitelist": members,
    }
