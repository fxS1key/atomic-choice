from pydantic import BaseModel, Field
from typing import Optional


class PollCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: str = Field(default="", max_length=1000)
    options: list[str] = Field(..., min_length=2, max_length=16)
    start_offset_seconds: int = Field(default=60, ge=0, description="Seconds from now")
    duration_seconds: int = Field(default=86400, ge=60, description="Duration in seconds")


class PollCreateWithCreator(PollCreate):
    """PollCreate + опциональный creator_wallet для per-poll whitelist."""
    creator_wallet: Optional[str] = Field(
        default=None,
        description="Кошелёк создателя голосования. Только этот адрес сможет управлять вайтлистом."
    )


class VoteRequest(BaseModel):
    poll_address: str
    option_index: int = Field(..., ge=0, le=15)
    wallet: str = Field(..., description="Voter wallet address (claimed)")
    signature: str = Field(
        ...,
        description="EIP-191 personal_sign of the message field, made with the voter's private key",
    )
    message: str = Field(
        ...,
        description="Plain-text message that was signed. Must match the canonical voting message.",
    )
    nonce: str = Field(..., description="Random nonce embedded in the signed message")


class MerkleProofResponse(BaseModel):
    commitment: str
    leaf_index: int
    path_elements: list[str]
    path_indices: list[int]
    root: str


class ConnectRequest(BaseModel):
    wallet: str


class AddStudentRequest(BaseModel):
    wallet: str
    name: str
    group: str
