"""
In-memory student registry.
Holds the mapping wallet → {name, group, secret, commitment}.
The secret is stored only server-side for the demo;
in production it never leaves the student's browser.
"""
from dataclasses import dataclass, field
from app.core.zk import student_secret, commitment_of


@dataclass
class Student:
    wallet: str          # checksummed
    name: str
    group: str
    secret: int          # demo: stored server-side
    commitment: int      # = poseidon1(secret)
    whitelisted: bool = False

    @property
    def wallet_short(self) -> str:
        return self.wallet[:6] + "…" + self.wallet[-4:]

    @property
    def commitment_hex(self) -> str:
        return hex(self.commitment)


# ── Seed test students ────────────────────────────────────────────────────────

_SEED = [
    ("0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266", "Алексей Петров",     "ИТ-31"),
    ("0x70997970C51812dc3A010C7d01b50e0d17dc79C8", "Мария Сидорова",     "ИТ-31"),
    ("0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC", "Дмитрий Козлов",     "ИТ-32"),
    ("0x90F79bf6EB2c4f870365E785982E1f101E93b906", "Анна Новикова",      "ИТ-32"),
    ("0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65", "Иван Морозов",       "ИТ-33"),
    ("0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc", "Екатерина Волкова",  "ИТ-33"),
    ("0x976EA74026E726554dB657fA54763abd0C3a0aa9", "Сергей Лебедев",    "ИТ-34"),
    ("0x14dC79964da2C08b23698B3D3cc7Ca32193d9955", "Ольга Соколова",    "ИТ-34"),
]


def _make_seed_students() -> dict[str, Student]:
    result = {}
    for wallet, name, group in _SEED:
        sec = student_secret(wallet)
        result[wallet.lower()] = Student(
            wallet=wallet,
            name=name,
            group=group,
            secret=sec,
            commitment=commitment_of(sec),
        )
    return result


# Singleton registry
_registry: dict[str, Student] = _make_seed_students()


def get_all() -> list[Student]:
    return list(_registry.values())


def get_by_wallet(wallet: str) -> Student | None:
    return _registry.get(wallet.lower())


def add_student(wallet: str, name: str, group: str) -> Student:
    sec = student_secret(wallet)
    s = Student(
        wallet=wallet,
        name=name,
        group=group,
        secret=sec,
        commitment=commitment_of(sec),
    )
    _registry[wallet.lower()] = s
    return s


def mark_whitelisted(wallet: str):
    s = _registry.get(wallet.lower())
    if s:
        s.whitelisted = True
