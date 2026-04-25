from fastapi import APIRouter, HTTPException
from app.models.student import get_all, get_by_wallet
from app.core.zk import nullifier_of

router = APIRouter(prefix="/api", tags=["students"])


def _student_payload(s) -> dict:
    poll_wl = [addr for addr, ok in s.poll_whitelisted.items() if ok]
    return {
        "wallet":           s.wallet,
        "name":             s.name,
        "group":            s.group,
        "commitment":       str(s.commitment),
        "whitelisted":      s.whitelisted,
        "poll_whitelisted": poll_wl,
        "eligible":         s.whitelisted or bool(poll_wl),
    }


@router.get("/students")
async def list_students():
    return [_student_payload(s) for s in get_all()]


@router.get("/students/{wallet}")
async def get_student(wallet: str):
    s = get_by_wallet(wallet)
    if not s:
        raise HTTPException(status_code=404, detail="Student not found")
    return _student_payload(s)


@router.get("/students/{wallet}/nullifier/{poll_id}")
async def get_nullifier(wallet: str, poll_id: int):
    """Returns the nullifier hash for (wallet, pollId). Demo only — never expose in prod."""
    s = get_by_wallet(wallet)
    if not s:
        raise HTTPException(status_code=404, detail="Student not found")
    n = nullifier_of(s.secret, poll_id)
    return {"nullifier": str(n), "nullifier_hex": hex(n)}
