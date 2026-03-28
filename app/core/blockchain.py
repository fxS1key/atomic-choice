"""
Blockchain connection layer.
Manages Web3 instance, loads contract ABIs/addresses,
provides typed contract accessors.
"""
import json
import logging
import os
from pathlib import Path
from typing import Optional

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

from app.core.config import settings

logger = logging.getLogger("atomic-choice.blockchain")

# ── ABIs ──────────────────────────────────────────────────────────────────────
# These match exactly the deployed contracts from contracts/contracts/*.sol

WHITELIST_ABI = [
    {"inputs":[{"internalType":"address","name":"_poseidon","type":"address"},{"internalType":"uint8","name":"_depth","type":"uint8"},{"internalType":"address","name":"admin","type":"address"}],"stateMutability":"nonpayable","type":"constructor"},
    {"inputs":[{"internalType":"uint256","name":"commitment","type":"uint256"}],"name":"addCommitment","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"internalType":"uint256[]","name":"commitments","type":"uint256[]"}],"name":"addCommitmentBatch","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"internalType":"uint256","name":"commitment","type":"uint256"}],"name":"revokeCommitment","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[],"name":"root","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"size","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"depth","outputs":[{"internalType":"uint8","name":"","type":"uint8"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"internalType":"uint256","name":"","type":"uint256"}],"name":"isCommitment","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"internalType":"uint256","name":"","type":"uint256"}],"name":"commitmentIndex","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"anonymous":False,"inputs":[{"indexed":True,"internalType":"uint256","name":"commitment","type":"uint256"},{"indexed":False,"internalType":"uint256","name":"leafIndex","type":"uint256"},{"indexed":False,"internalType":"uint256","name":"newRoot","type":"uint256"}],"name":"CommitmentAdded","type":"event"},
    {"anonymous":False,"inputs":[{"indexed":True,"internalType":"uint256","name":"commitment","type":"uint256"}],"name":"CommitmentRevoked","type":"event"},
]

FACTORY_ABI = [
    {"inputs":[{"internalType":"address","name":"_whitelist","type":"address"},{"internalType":"address","name":"_verifier","type":"address"},{"internalType":"address","name":"admin","type":"address"}],"stateMutability":"nonpayable","type":"constructor"},
    {"inputs":[{"internalType":"string","name":"title","type":"string"},{"internalType":"string","name":"description","type":"string"},{"internalType":"uint8","name":"options","type":"uint8"},{"internalType":"uint256","name":"startTime","type":"uint256"},{"internalType":"uint256","name":"endTime","type":"uint256"}],"name":"createPoll","outputs":[{"internalType":"uint256","name":"pollId","type":"uint256"},{"internalType":"address","name":"pollAddr","type":"address"}],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[],"name":"totalPolls","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"internalType":"uint256","name":"pollId","type":"uint256"}],"name":"polls","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"internalType":"uint256","name":"offset","type":"uint256"},{"internalType":"uint256","name":"limit","type":"uint256"}],"name":"getPolls","outputs":[{"internalType":"address[]","name":"result","type":"address[]"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"whitelist","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"nextPollId","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"anonymous":False,"inputs":[{"indexed":True,"internalType":"uint256","name":"pollId","type":"uint256"},{"indexed":True,"internalType":"address","name":"pollAddress","type":"address"},{"indexed":True,"internalType":"address","name":"creator","type":"address"},{"indexed":False,"internalType":"string","name":"title","type":"string"},{"indexed":False,"internalType":"uint256","name":"startTime","type":"uint256"},{"indexed":False,"internalType":"uint256","name":"endTime","type":"uint256"}],"name":"PollCreated","type":"event"},
]

POLL_ABI = [
    {"inputs":[],"name":"pollId","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"title","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"description","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"startTime","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"endTime","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"optionsCount","outputs":[{"internalType":"uint8","name":"","type":"uint8"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"state","outputs":[{"internalType":"uint8","name":"","type":"uint8"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"totalVotes","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"isActive","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"getResults","outputs":[{"internalType":"uint256[]","name":"","type":"uint256[]"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"internalType":"uint256","name":"","type":"uint256"}],"name":"nullifierUsed","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"internalType":"uint256","name":"","type":"uint256"}],"name":"validRoots","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"internalType":"uint8","name":"","type":"uint8"}],"name":"votes","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"internalType":"uint256","name":"nullifierHash","type":"uint256"},{"internalType":"uint256","name":"merkleRoot","type":"uint256"},{"internalType":"uint8","name":"vote","type":"uint8"},{"internalType":"uint256[2]","name":"pA","type":"uint256[2]"},{"internalType":"uint256[2][2]","name":"pB","type":"uint256[2][2]"},{"internalType":"uint256[2]","name":"pC","type":"uint256[2]"}],"name":"castVote","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"internalType":"uint256","name":"newRoot","type":"uint256"}],"name":"addWhitelistRoot","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[],"name":"endPoll","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"anonymous":False,"inputs":[{"indexed":True,"internalType":"uint256","name":"nullifierHash","type":"uint256"},{"indexed":True,"internalType":"uint8","name":"option","type":"uint8"}],"name":"VoteCast","type":"event"},
    {"anonymous":False,"inputs":[{"indexed":False,"internalType":"uint256","name":"totalVotes","type":"uint256"}],"name":"PollEnded","type":"event"},
]


# ── Web3 singleton ─────────────────────────────────────────────────────────────

_w3: Optional[Web3] = None


def get_w3() -> Web3:
    global _w3
    if _w3 is None:
        _w3 = Web3(Web3.HTTPProvider(settings.HARDHAT_RPC_URL))
        _w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return _w3


def is_connected() -> bool:
    try:
        return get_w3().is_connected()
    except Exception:
        return False


def sync_chain_time():
    """Advance Hardhat block.timestamp to match system clock."""
    import time
    w3 = get_w3()
    now = int(time.time())
    chain_ts = w3.eth.get_block("latest")["timestamp"]
    if now > chain_ts:
        w3.provider.make_request("evm_setNextBlockTimestamp", [now])
        w3.provider.make_request("evm_mine", [])
        logger.debug("Chain time synced: %d → %d", chain_ts, now)


def get_deployer_account():
    w3 = get_w3()
    account = w3.eth.account.from_key(settings.DEPLOYER_PRIVATE_KEY)
    return account


# ── Contract factories ─────────────────────────────────────────────────────────

def get_whitelist_contract():
    if not settings.WHITELIST_ADDRESS:
        raise RuntimeError("WHITELIST_ADDRESS not set — run /api/admin/deploy first")
    w3 = get_w3()
    return w3.eth.contract(
        address=Web3.to_checksum_address(settings.WHITELIST_ADDRESS),
        abi=WHITELIST_ABI,
    )


def get_factory_contract():
    if not settings.FACTORY_ADDRESS:
        raise RuntimeError("FACTORY_ADDRESS not set — run /api/admin/deploy first")
    w3 = get_w3()
    return w3.eth.contract(
        address=Web3.to_checksum_address(settings.FACTORY_ADDRESS),
        abi=FACTORY_ABI,
    )


def get_poll_contract(address: str):
    w3 = get_w3()
    return w3.eth.contract(
        address=Web3.to_checksum_address(address),
        abi=POLL_ABI,
    )


# ── Transaction helper ─────────────────────────────────────────────────────────

def send_tx(contract_fn, from_address: str, private_key: str, value: int = 0) -> dict:
    """
    Builds, signs and sends a transaction. Returns receipt dict.
    Logs the tx hash so it appears in Hardhat node console.
    """
    w3 = get_w3()
    nonce = w3.eth.get_transaction_count(Web3.to_checksum_address(from_address))
    gas_estimate = contract_fn.estimate_gas({"from": Web3.to_checksum_address(from_address)})

    tx = contract_fn.build_transaction({
        "from": Web3.to_checksum_address(from_address),
        "nonce": nonce,
        "gas": int(gas_estimate * 1.2),
        "gasPrice": w3.eth.gas_price,
        "value": value,
        "chainId": settings.CHAIN_ID,
    })

    signed = w3.eth.account.sign_transaction(tx, private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

    logger.info(
        "TX confirmed | hash=%s | block=%s | gas=%s | status=%s",
        tx_hash.hex(),
        receipt["blockNumber"],
        receipt["gasUsed"],
        "✓ success" if receipt["status"] == 1 else "✗ reverted",
    )
    return receipt


def load_deployments() -> dict:
    path = Path(settings.DEPLOYMENTS_FILE)
    if path.exists():
        return json.loads(path.read_text())
    return {}


def save_deployments(data: dict):
    path = Path(settings.DEPLOYMENTS_FILE)
    path.write_text(json.dumps(data, indent=2))
    # Also update live settings
    settings.FACTORY_ADDRESS   = data.get("factory")
    settings.WHITELIST_ADDRESS = data.get("whitelist")
    settings.VERIFIER_ADDRESS  = data.get("verifier")
    settings.POSEIDON_ADDRESS  = data.get("poseidon")
