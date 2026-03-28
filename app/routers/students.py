from fastapi import APIRouter, HTTPException
from app.models.student import get_all, get_by_wallet
from app.core.zk import nullifier_of

router = APIRouter(prefix="/api", tags=["students"])


@router.get("/students")
async def list_students():
    students = get_all()
    return [
        {
            "wallet":      s.wallet,
            "name":        s.name,
            "group":       s.group,
            "commitment":  str(s.commitment),
            "whitelisted": s.whitelisted,
        }
        for s in students
    ]


@router.get("/students/{wallet}")
async def get_student(wallet: str):
    s = get_by_wallet(wallet)
    if not s:
        raise HTTPException(status_code=404, detail="Student not found")
    return {
        "wallet":      s.wallet,
        "name":        s.name,
        "group":       s.group,
        "commitment":  str(s.commitment),
        "whitelisted": s.whitelisted,
    }


@router.get("/students/{wallet}/nullifier/{poll_id}")
async def get_nullifier(wallet: str, poll_id: int):
    """Returns the nullifier hash for (wallet, pollId). Demo only — never expose in prod."""
    s = get_by_wallet(wallet)
    if not s:
        raise HTTPException(status_code=404, detail="Student not found")
    n = nullifier_of(s.secret, poll_id)
    return {"nullifier": str(n), "nullifier_hex": hex(n)}
