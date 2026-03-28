// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "./IncrementalMerkleTree.sol";
import "./PoseidonT3.sol";

/**
 * @title Whitelist
 * @notice Manages the set of eligible voters as an incremental Merkle Tree.
 *
 *  Roles:
 *    DEFAULT_ADMIN_ROLE  — university admin; can add/remove admins
 *    ADMIN_ROLE          — can add and remove identity commitments
 *
 *  Flow:
 *    1. Admin deploys this contract with a Poseidon address and tree depth.
 *    2. Admin calls addCommitment(identity) for each student.
 *    3. The current root is passed to VotingFactory when creating a poll.
 *    4. Students prove Merkle membership off-chain (ZK proof) and submit on-chain.
 *
 *  Identity commitment:
 *    identityCommitment = Poseidon(identitySecret)
 *    nullifier           = Poseidon(identitySecret, pollId)
 *
 *  The contract never stores the identitySecret — only the commitment.
 */
contract Whitelist is AccessControl, ReentrancyGuard {
    using IncrementalMerkleTree for IncrementalMerkleTree.Tree;

    // ------------------------------------------------------------------
    //  Roles
    // ------------------------------------------------------------------
    bytes32 public constant ADMIN_ROLE = keccak256("ADMIN_ROLE");

    // ------------------------------------------------------------------
    //  State
    // ------------------------------------------------------------------
    IncrementalMerkleTree.Tree private _tree;
    IPoseidonT3 public immutable poseidon;

    /// commitment → leaf index (1-based; 0 means not present)
    mapping(uint256 => uint256) public commitmentIndex;

    /// commitment → whether it was ever added
    mapping(uint256 => bool) public isCommitment;

    // ------------------------------------------------------------------
    //  Events
    // ------------------------------------------------------------------
    event CommitmentAdded(uint256 indexed commitment, uint256 leafIndex, uint256 newRoot);
    event CommitmentRevoked(uint256 indexed commitment);

    // ------------------------------------------------------------------
    //  Constructor
    // ------------------------------------------------------------------

    /**
     * @param _poseidon  Address of deployed PoseidonT3 contract.
     * @param _depth     Merkle tree depth (e.g. 20 → supports 1 048 576 students).
     * @param admin      Address of the initial admin.
     */
    constructor(
        address _poseidon,
        uint8   _depth,
        address admin
    ) {
        require(_poseidon != address(0), "Whitelist: zero poseidon");
        require(admin     != address(0), "Whitelist: zero admin");

        poseidon = IPoseidonT3(_poseidon);
        _tree.init(_depth);

        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(ADMIN_ROLE,         admin);
    }

    // ------------------------------------------------------------------
    //  Admin functions
    // ------------------------------------------------------------------

    /**
     * @notice Adds a student identity commitment to the Merkle tree.
     * @param commitment  Poseidon(identitySecret) — computed client-side.
     */
    function addCommitment(uint256 commitment)
        external
        onlyRole(ADMIN_ROLE)
        nonReentrant
    {
        require(commitment != 0,                     "Whitelist: zero commitment");
        require(!isCommitment[commitment],            "Whitelist: already added");
        require(
            commitment < IncrementalMerkleTree.SNARK_SCALAR_FIELD,
            "Whitelist: commitment out of field"
        );

        uint256 index = _tree.insert(commitment, poseidon);

        commitmentIndex[commitment] = index + 1; // store 1-based
        isCommitment[commitment]    = true;

        emit CommitmentAdded(commitment, index, _tree.root);
    }

    /**
     * @notice Batch-adds multiple commitments in one transaction (gas savings).
     */
    function addCommitmentBatch(uint256[] calldata commitments)
        external
        onlyRole(ADMIN_ROLE)
        nonReentrant
    {
        for (uint256 i = 0; i < commitments.length; i++) {
            uint256 c = commitments[i];
            require(c != 0,                  "Whitelist: zero commitment");
            require(!isCommitment[c],         "Whitelist: already added");
            require(
                c < IncrementalMerkleTree.SNARK_SCALAR_FIELD,
                "Whitelist: out of field"
            );

            uint256 index = _tree.insert(c, poseidon);
            commitmentIndex[c] = index + 1;
            isCommitment[c]    = true;

            emit CommitmentAdded(c, index, _tree.root);
        }
    }

    /**
     * @notice Marks a commitment as revoked (does not modify the tree —
     *         the leaf stays in place so existing proofs remain valid against
     *         the same root, but VotingPoll checks `isCommitment` for new polls).
     *
     *  Note: True removal would require a different tree structure (e.g. a
     *        nullifier for the revoked commitment). For a university setting
     *        with a relatively stable student list, this is acceptable.
     */
    function revokeCommitment(uint256 commitment)
        external
        onlyRole(ADMIN_ROLE)
    {
        require(isCommitment[commitment], "Whitelist: not found");
        isCommitment[commitment] = false;
        emit CommitmentRevoked(commitment);
    }

    // ------------------------------------------------------------------
    //  View functions
    // ------------------------------------------------------------------

    /// @notice Current Merkle root.
    function root() external view returns (uint256) {
        return _tree.root;
    }

    /// @notice Number of registered students.
    function size() external view returns (uint256) {
        return _tree.size;
    }

    /// @notice Depth of the tree.
    function depth() external view returns (uint8) {
        return _tree.depth;
    }
}
