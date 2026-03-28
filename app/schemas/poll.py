from pydantic import BaseModel, Field
from typing import Optional


class PollCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: str = Field(default="", max_length=1000)
    options: list[str] = Field(..., min_length=2, max_length=16)
    start_offset_seconds: int = Field(default=60, ge=0, description="Seconds from now")
    duration_seconds: int = Field(default=86400, ge=60, description="Duration in seconds")


class VoteRequest(BaseModel):
    poll_address: str
    option_index: int = Field(..., ge=0, le=15)
    wallet: str = Field(..., description="Voter wallet address")


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
