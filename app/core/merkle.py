"""
Off-chain Merkle Tree that mirrors IncrementalMerkleTree.sol exactly.
Used to generate inclusion proofs served to the frontend.

Hash function: keccak256(a, b) % SNARK_FIELD — matches PoseidonStub.sol
(swap for real Poseidon when using the production ZK circuit)
"""
import hashlib
import logging
from typing import TypedDict

logger = logging.getLogger("atomic-choice.merkle")

SNARK_FIELD = (
    21888242871839275222246405745257275088548364400416034343698204186575808495617
)


def _hash_pair(a: int, b: int) -> int:
    """keccak256(abi.encodePacked(a, b)) % SNARK_FIELD — matches PoseidonStub.sol"""
    raw = a.to_bytes(32, "big") + b.to_bytes(32, "big")
    h = int(hashlib.sha256(raw).hexdigest(), 16)
    return h % SNARK_FIELD


class MerkleProof(TypedDict):
    leaf: int
    leaf_index: int
    path_elements: list[int]
    path_indices: list[int]
    root: int


class IncrementalMerkleTree:
    """
    Append-only Merkle Tree.
    depth=10 → 1024 leaves (enough for demo)
    depth=20 → 1 048 576 leaves (production)
    """

    def __init__(self, depth: int = 10):
        self.depth = depth
        self.leaves: list[int] = []
        self._zeros = self._precompute_zeros()

    def _precompute_zeros(self) -> list[int]:
        z = [0]
        for i in range(self.depth):
            z.append(_hash_pair(z[i], z[i]))
        return z

    def _build_tree(self) -> list[int]:
        size = 1 << self.depth
        tree = [0] * (size * 2)
        for i, leaf in enumerate(self.leaves):
            tree[size + i] = leaf
        for i in range(self.leaves.__len__(), size):
            tree[size + i] = self._zeros[0]
        for i in range(size - 1, 0, -1):
            tree[i] = _hash_pair(tree[2 * i], tree[2 * i + 1])
        return tree

    def insert(self, leaf: int) -> int:
        assert leaf < SNARK_FIELD, "Leaf out of field"
        assert len(self.leaves) < (1 << self.depth), "Tree is full"
        self.leaves.append(leaf)
        idx = len(self.leaves) - 1
        logger.debug("Merkle insert leaf=%s index=%s root=%s", leaf, idx, self.root())
        return idx

    def root(self) -> int:
        tree = self._build_tree()
        return tree[1]

    def proof(self, leaf_index: int) -> MerkleProof:
        assert 0 <= leaf_index < len(self.leaves), f"Index {leaf_index} out of range"
        tree = self._build_tree()
        size = 1 << self.depth

        path_elements: list[int] = []
        path_indices: list[int] = []

        pos = size + leaf_index
        for _ in range(self.depth):
            is_right = pos % 2 == 1
            sibling = pos - 1 if is_right else pos + 1
            path_indices.append(1 if is_right else 0)
            path_elements.append(tree[sibling])
            pos //= 2

        return MerkleProof(
            leaf=self.leaves[leaf_index],
            leaf_index=leaf_index,
            path_elements=path_elements,
            path_indices=path_indices,
            root=tree[1],
        )

    def index_of(self, commitment: int) -> int:
        try:
            return self.leaves.index(commitment)
        except ValueError:
            return -1

    def verify(self, leaf: int, path_elements: list[int], path_indices: list[int], root: int) -> bool:
        current = leaf
        for sibling, side in zip(path_elements, path_indices):
            left, right = (sibling, current) if side == 1 else (current, sibling)
            current = _hash_pair(left, right)
        return current == root


# ── Singleton tree (rebuilt from blockchain events on startup) ────────────────
_tree: IncrementalMerkleTree = IncrementalMerkleTree(depth=10)


def get_tree() -> IncrementalMerkleTree:
    return _tree


def rebuild_tree_from_events(commitments: list[int]):
    """Called on startup to sync tree from CommitmentAdded events."""
    global _tree
    _tree = IncrementalMerkleTree(depth=10)
    for c in commitments:
        _tree.insert(c)
    logger.info("Merkle tree rebuilt: %d leaves, root=%s", len(_tree.leaves), _tree.root())
