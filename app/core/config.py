from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # App
    APP_TITLE: str = "Atomic Choice"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # Blockchain
    HARDHAT_RPC_URL: str = "http://127.0.0.1:8545"
    CHAIN_ID: int = 31337

    # Contracts (populated after deploy)
    FACTORY_ADDRESS: Optional[str] = None
    WHITELIST_ADDRESS: Optional[str] = None
    VERIFIER_ADDRESS: Optional[str] = None
    POSEIDON_ADDRESS: Optional[str] = None

    # Deployer (Hardhat account #0 default)
    DEPLOYER_PRIVATE_KEY: str = (
        "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
    )
    DEPLOYER_ADDRESS: str = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"

    # Paths
    ARTIFACTS_DIR: str = "contracts/artifacts"
    DEPLOYMENTS_FILE: str = "deployments.json"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
