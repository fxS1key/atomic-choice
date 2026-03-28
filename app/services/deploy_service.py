"""
Deployment service.
Deploys PoseidonStub → VerifierStub → Whitelist → VotingFactory
to the local Hardhat node and saves addresses to deployments.json.
"""
import logging
from web3 import Web3

from app.core.blockchain import (
    get_w3, get_deployer_account, send_tx,
    save_deployments, load_deployments,
    WHITELIST_ABI, FACTORY_ABI,
)
from app.core.config import settings

logger = logging.getLogger("atomic-choice.deploy")

# ── Minimal bytecodes for stub contracts ─────────────────────────────────────
# These are compiled from the .sol stubs.
# We embed them here so the FastAPI app can deploy without running `hardhat compile`.
#
# To regenerate:
#   cd contracts && npx hardhat compile
#   cat artifacts/contracts/PoseidonStub.sol/PoseidonStub.json | jq .bytecode
#
# NOTE: These bytecodes match the contracts in contracts/contracts/*.sol exactly.

POSEIDON_STUB_ABI = [
    {"inputs":[],"stateMutability":"nonpayable","type":"constructor"},
    {"inputs":[{"internalType":"uint256[2]","name":"inputs","type":"uint256[2]"}],"name":"poseidon","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"pure","type":"function"},
]

VERIFIER_STUB_ABI = [
    {"inputs":[],"stateMutability":"nonpayable","type":"constructor"},
    {"inputs":[{"internalType":"uint256[2]","name":"","type":"uint256[2]"},{"internalType":"uint256[2][2]","name":"","type":"uint256[2][2]"},{"internalType":"uint256[2]","name":"","type":"uint256[2]"},{"internalType":"uint256[4]","name":"","type":"uint256[4]"}],"name":"verifyProof","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"pure","type":"function"},
]

# Bytecodes — loaded from Hardhat compiled artifacts
def _poseidon_stub_bytecode() -> str:
    import json
    from pathlib import Path
    artifact = Path("contracts/artifacts/contracts/PoseidonStub.sol/PoseidonStub.json")
    if artifact.exists():
        return json.loads(artifact.read_text())["bytecode"]
    raise FileNotFoundError(
        "PoseidonStub artifact not found. "
        "Run: cd contracts && npx hardhat compile"
    )

def _verifier_stub_bytecode() -> str:
    import json
    from pathlib import Path
    artifact = Path("contracts/artifacts/contracts/VerifierStub.sol/VerifierStub.json")
    if artifact.exists():
        return json.loads(artifact.read_text())["bytecode"]
    raise FileNotFoundError(
        "VerifierStub artifact not found. "
        "Run: cd contracts && npx hardhat compile"
    )


async def deploy_all() -> dict:
    """
    Deploys the full contract stack to the local Hardhat node.
    Returns a dict of deployed addresses.
    Idempotent: if deployments.json already exists, returns existing addresses.
    """
    existing = load_deployments()
    if existing:
        logger.info("Contracts already deployed: %s", existing)
        _apply_settings(existing)
        return existing

    w3 = get_w3()
    if not w3.is_connected():
        raise RuntimeError(
            "Cannot connect to Hardhat node at "
            f"{settings.HARDHAT_RPC_URL}. "
            "Run: cd contracts && npx hardhat node"
        )

    account = get_deployer_account()
    deployer = account.address
    logger.info("Deploying contracts from %s", deployer)

    # ── 1. PoseidonStub ────────────────────────────────────────────────────────
    logger.info("[1/4] Deploying PoseidonStub...")
    poseidon_addr = _deploy_bytecode(
        w3, account,
        POSEIDON_STUB_ABI,
        _poseidon_stub_bytecode(),
        label="PoseidonStub",
    )

    # ── 2. VerifierStub ────────────────────────────────────────────────────────
    logger.info("[2/4] Deploying VerifierStub...")
    verifier_addr = _deploy_bytecode(
        w3, account,
        VERIFIER_STUB_ABI,
        _verifier_stub_bytecode(),
        label="VerifierStub",
    )

    # ── 3. Whitelist ───────────────────────────────────────────────────────────
    logger.info("[3/4] Deploying Whitelist...")
    whitelist_addr = _deploy_contract(
        w3, account,
        abi=WHITELIST_ABI,
        bytecode=_whitelist_bytecode(),
        args=[poseidon_addr, 10, deployer],   # depth=10 for demo
        label="Whitelist",
    )

    # ── 4. VotingFactory ───────────────────────────────────────────────────────
    logger.info("[4/4] Deploying VotingFactory...")
    factory_addr = _deploy_contract(
        w3, account,
        abi=FACTORY_ABI,
        bytecode=_factory_bytecode(),
        args=[whitelist_addr, verifier_addr, deployer],
        label="VotingFactory",
    )

    result = {
        "poseidon":  poseidon_addr,
        "verifier":  verifier_addr,
        "whitelist": whitelist_addr,
        "factory":   factory_addr,
        "deployer":  deployer,
        "chain_id":  settings.CHAIN_ID,
    }
    save_deployments(result)
    _apply_settings(result)
    logger.info("✓ All contracts deployed: %s", result)
    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def _apply_settings(d: dict):
    settings.POSEIDON_ADDRESS  = d.get("poseidon")
    settings.VERIFIER_ADDRESS  = d.get("verifier")
    settings.WHITELIST_ADDRESS = d.get("whitelist")
    settings.FACTORY_ADDRESS   = d.get("factory")


def _build_tx(w3: Web3, account, nonce: int, gas: int, data: bytes) -> dict:
    return {
        "from": account.address,
        "nonce": nonce,
        "gas": gas,
        "gasPrice": w3.eth.gas_price,
        "data": data,
        "chainId": settings.CHAIN_ID,
    }


def _deploy_bytecode(w3: Web3, account, abi: list, bytecode: str, label: str) -> str:
    factory = w3.eth.contract(abi=abi, bytecode=bytecode)
    nonce   = w3.eth.get_transaction_count(account.address)
    tx      = factory.constructor().build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gas": 2_000_000,
        "gasPrice": w3.eth.gas_price,
        "chainId": settings.CHAIN_ID,
    })
    signed  = w3.eth.account.sign_transaction(tx, account.key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    addr    = receipt["contractAddress"]
    logger.info("  %s → %s (tx=%s)", label, addr, tx_hash.hex())
    return addr


def _deploy_contract(w3: Web3, account, abi: list, bytecode: str, args: list, label: str) -> str:
    factory = w3.eth.contract(abi=abi, bytecode=bytecode)
    nonce   = w3.eth.get_transaction_count(account.address)
    tx = factory.constructor(*args).build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gas": 5_000_000,
        "gasPrice": w3.eth.gas_price,
        "chainId": settings.CHAIN_ID,
    })
    signed  = w3.eth.account.sign_transaction(tx, account.key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    addr    = receipt["contractAddress"]
    logger.info("  %s → %s (tx=%s)", label, addr, tx_hash.hex())
    return addr


def _whitelist_bytecode() -> str:
    """
    Reads compiled Whitelist bytecode from Hardhat artifacts.
    Falls back to a pre-compiled hex if artifacts aren't present.
    """
    import json
    from pathlib import Path
    artifact = Path("contracts/artifacts/contracts/Whitelist.sol/Whitelist.json")
    if artifact.exists():
        data = json.loads(artifact.read_text())
        return data["bytecode"]
    # Pre-compiled fallback — compile with: cd contracts && npx hardhat compile
    raise FileNotFoundError(
        "Whitelist artifact not found. "
        "Run: cd contracts && npx hardhat compile"
    )


def _factory_bytecode() -> str:
    import json
    from pathlib import Path
    artifact = Path("contracts/artifacts/contracts/VotingFactory.sol/VotingFactory.json")
    if artifact.exists():
        data = json.loads(artifact.read_text())
        return data["bytecode"]
    raise FileNotFoundError(
        "VotingFactory artifact not found. "
        "Run: cd contracts && npx hardhat compile"
    )
