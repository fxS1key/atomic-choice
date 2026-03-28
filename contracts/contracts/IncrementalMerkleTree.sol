// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./PoseidonT3.sol";

/**
 * @title IncrementalMerkleTree
 * @notice An append-only Merkle Tree where leaves are added one by one.
 *         Internal nodes are computed with Poseidon hash (ZK-friendly).
 *
 *  Properties:
 *    - Depth D → up to 2^D leaves
 *    - O(D) gas per insertion
 *    - Root is updated on every insertion
 *
 *  Based on the incremental Merkle tree used by Semaphore v3/v4.
 */
library IncrementalMerkleTree {
    uint8 internal constant MAX_DEPTH = 32;

    // Z[i] = hash of a subtree of depth i with all-zero leaves.
    // Precomputed for the keccak-based stub; replace with Poseidon zeros in prod.
    // z[0] = 0  (empty leaf)
    // z[i] = Poseidon(z[i-1], z[i-1])
    uint256 internal constant SNARK_SCALAR_FIELD =
        21888242871839275222246405745257275088548364400416034343698204186575808495617;

    struct Tree {
        uint8  depth;          // fixed depth (e.g. 20 for 1M students)
        uint256 size;          // number of inserted leaves
        uint256 root;          // current Merkle root
        uint256[MAX_DEPTH] filledSubtrees; // running hashes at each level
    }

    // ------------------------------------------------------------------ //
    //  Initialise
    // ------------------------------------------------------------------ //

    function init(Tree storage self, uint8 depth) internal {
        require(depth > 0 && depth <= MAX_DEPTH, "IMT: invalid depth");
        self.depth = depth;

        // Compute zero values bottom-up using the stub hash
        uint256 zero = 0;
        for (uint8 i = 0; i < depth; i++) {
            self.filledSubtrees[i] = zero;
            zero = _hashPair(zero, zero);
        }
        self.root = zero;
    }

    // ------------------------------------------------------------------ //
    //  Insert
    // ------------------------------------------------------------------ //

    /**
     * @notice Appends a leaf and recomputes the root.
     * @return index  The 0-based index of the inserted leaf.
     */
    function insert(
        Tree storage self,
        uint256 leaf,
        IPoseidonT3 poseidon
    ) internal returns (uint256 index) {
        require(self.size < (1 << self.depth), "IMT: tree is full");
        require(leaf < SNARK_SCALAR_FIELD, "IMT: leaf out of field");

        index = self.size;
        uint256 current = leaf;
        uint256 currentIndex = index;

        for (uint8 i = 0; i < self.depth; i++) {
            uint256 left;
            uint256 right;

            if (currentIndex % 2 == 0) {
                // current node is a left child → store it, right sibling is zero
                left = current;
                right = _zeroValue(poseidon, i);
                self.filledSubtrees[i] = current;
            } else {
                // current node is a right child → left sibling is already stored
                left = self.filledSubtrees[i];
                right = current;
            }

            current = address(poseidon) != address(0)
                ? poseidon.poseidon([left, right])
                : _hashPair(left, right);

            currentIndex >>= 1;
        }

        self.root = current;
        self.size++;
        return index;
    }

    // ------------------------------------------------------------------ //
    //  Proof verification (off-chain proof → on-chain check)
    // ------------------------------------------------------------------ //

    /**
     * @notice Verifies a Merkle inclusion proof.
     * @param leaf        The leaf value to verify.
     * @param pathIndices Array of 0/1 indicating left/right at each level.
     * @param siblings    Sibling hashes at each level.
     * @param root        The expected Merkle root.
     */
    function verifyProof(
        uint256 leaf,
        uint8[] calldata pathIndices,
        uint256[] calldata siblings,
        uint256 root,
        IPoseidonT3 poseidon
    ) internal view returns (bool) {
        require(pathIndices.length == siblings.length, "IMT: proof length mismatch");

        uint256 current = leaf;
        for (uint256 i = 0; i < pathIndices.length; i++) {
            uint256 left;
            uint256 right;
            if (pathIndices[i] == 0) {
                left = current;
                right = siblings[i];
            } else {
                left = siblings[i];
                right = current;
            }
            current = address(poseidon) != address(0)
                ? poseidon.poseidon([left, right])
                : _hashPair(left, right);
        }
        return current == root;
    }

    // ------------------------------------------------------------------ //
    //  Internal helpers
    // ------------------------------------------------------------------ //

    function _hashPair(uint256 a, uint256 b) internal pure returns (uint256) {
        return uint256(keccak256(abi.encodePacked(a, b))) % SNARK_SCALAR_FIELD;
    }

    /**
     * @dev Returns the zero value for depth level i.
     *      If a real Poseidon is available, compute it; otherwise use keccak stub.
     */
    function _zeroValue(IPoseidonT3 poseidon, uint8 level)
        internal
        view
        returns (uint256 zero)
    {
        zero = 0;
        for (uint8 i = 0; i < level; i++) {
            zero = address(poseidon) != address(0)
                ? poseidon.poseidon([zero, zero])
                : _hashPair(zero, zero);
        }
    }
}
