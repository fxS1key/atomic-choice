// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "./IVerifier.sol";

/**
 * @title VotingPoll
 * @notice A single anonymous voting poll protected by ZK proofs.
 *
 *  Lifecycle:
 *    Created  → Active (after startTime)
 *             → Ended  (after endTime or manual close by admin)
 *
 *  ZK Proof layout (public signals):
 *    [0] nullifierHash  — Poseidon(identitySecret, pollId); prevents double-vote
 *    [1] merkleRoot     — must match a known root in Whitelist
 *    [2] vote           — option index (0-based)
 *    [3] pollId         — must match this contract's pollId
 *
 *  Security properties:
 *    ✔  Anonymous      — nullifier reveals nothing about the voter
 *    ✔  Non-reusable   — nullifier stored; resubmission reverts
 *    ✔  Whitelisted    — Merkle root must be a valid whitelist root
 *    ✔  Bounded        — vote must be a valid option index
 *    ✔  Time-locked    — votes only accepted between startTime and endTime
 */
contract VotingPoll is Ownable, ReentrancyGuard {
    // ------------------------------------------------------------------
    //  Types
    // ------------------------------------------------------------------
    enum State { Active, Ended }

    // ------------------------------------------------------------------
    //  Immutables
    // ------------------------------------------------------------------
    IVerifier public immutable verifier;

    uint256 public immutable pollId;
    string  public           title;
    string  public           description; // IPFS CID or plain text
    uint256 public immutable startTime;
    uint256 public immutable endTime;
    uint8   public immutable optionsCount;

    // ------------------------------------------------------------------
    //  State
    // ------------------------------------------------------------------
    State public state;

    /// Merkle roots that are accepted as valid whitelists for this poll.
    /// Multiple roots allow the poll to accept voters from different snapshots.
    mapping(uint256 => bool) public validRoots;

    /// nullifierHash → used; prevents double voting
    mapping(uint256 => bool) public nullifierUsed;

    /// option index → vote count
    mapping(uint8 => uint256) public votes;

    uint256 public totalVotes;

    // ------------------------------------------------------------------
    //  Events
    // ------------------------------------------------------------------
    event VoteCast(uint256 indexed nullifierHash, uint8 indexed option);
    event PollEnded(uint256 totalVotes);
    event RootAdded(uint256 root);

    // ------------------------------------------------------------------
    //  Modifiers
    // ------------------------------------------------------------------
    modifier onlyActive() {
        require(state == State.Active,          "Poll: not active");
        require(block.timestamp >= startTime,   "Poll: not started yet");
        require(block.timestamp <= endTime,     "Poll: already ended");
        _;
    }

    // ------------------------------------------------------------------
    //  Constructor
    // ------------------------------------------------------------------

    /**
     * @param _pollId        Unique ID (used inside ZK circuit).
     * @param _title         Human-readable title.
     * @param _description   Description or IPFS CID.
     * @param _options       Number of voting options (2–16).
     * @param _startTime     Unix timestamp when voting opens.
     * @param _endTime       Unix timestamp when voting closes.
     * @param _whitelistRoot Initial Merkle root of eligible voters.
     * @param _verifier      Address of the Groth16 verifier contract.
     * @param _admin         Address that owns this poll.
     */
    constructor(
        uint256 _pollId,
        string  memory _title,
        string  memory _description,
        uint8   _options,
        uint256 _startTime,
        uint256 _endTime,
        uint256 _whitelistRoot,
        address _verifier,
        address _admin
    ) Ownable(_admin) {
        require(_options >= 2 && _options <= 16, "Poll: 2-16 options");
        require(_endTime > _startTime,            "Poll: bad time range");
        require(_verifier != address(0),          "Poll: zero verifier");
        require(_whitelistRoot != 0,              "Poll: zero root");

        pollId       = _pollId;
        title        = _title;
        description  = _description;
        optionsCount = _options;
        startTime    = _startTime;
        endTime      = _endTime;
        verifier     = IVerifier(_verifier);
        state        = State.Active;

        validRoots[_whitelistRoot] = true;
        emit RootAdded(_whitelistRoot);
    }

    // ------------------------------------------------------------------
    //  Vote
    // ------------------------------------------------------------------

    /**
     * @notice Cast an anonymous vote with a ZK proof.
     *
     * @param nullifierHash  Poseidon(identitySecret, pollId) — public signal [0].
     * @param merkleRoot     Whitelist Merkle root    — public signal [1].
     * @param vote           Option index (0-based)   — public signal [2].
     * @param pA             Proof point A.
     * @param pB             Proof point B.
     * @param pC             Proof point C.
     */
    function castVote(
        uint256           nullifierHash,
        uint256           merkleRoot,
        uint8             vote,
        uint256[2]    calldata pA,
        uint256[2][2] calldata pB,
        uint256[2]    calldata pC
    ) external onlyActive nonReentrant {
        // 1. Basic sanity checks
        require(vote < optionsCount,               "Poll: invalid option");
        require(!nullifierUsed[nullifierHash],      "Poll: already voted");
        require(validRoots[merkleRoot],             "Poll: unknown root");

        // 2. Verify ZK proof
        //    Public signals: [nullifierHash, merkleRoot, vote, pollId]
        uint256[4] memory pubSignals = [
            nullifierHash,
            merkleRoot,
            uint256(vote),
            pollId
        ];

        require(
            verifier.verifyProof(pA, pB, pC, pubSignals),
            "Poll: invalid proof"
        );

        // 3. Record nullifier (prevent double vote)
        nullifierUsed[nullifierHash] = true;

        // 4. Count vote
        votes[vote]++;
        totalVotes++;

        emit VoteCast(nullifierHash, vote);
    }

    // ------------------------------------------------------------------
    //  Admin
    // ------------------------------------------------------------------

    /**
     * @notice Add an additional whitelist root (e.g. after new students enrolled).
     *         Only callable by owner before the poll ends.
     */
    function addWhitelistRoot(uint256 newRoot) external onlyOwner {
        require(state == State.Active, "Poll: ended");
        require(newRoot != 0,          "Poll: zero root");
        validRoots[newRoot] = true;
        emit RootAdded(newRoot);
    }

    /**
     * @notice Manually end the poll before endTime.
     */
    function endPoll() external onlyOwner {
        require(state == State.Active, "Poll: already ended");
        state = State.Ended;
        emit PollEnded(totalVotes);
    }

    // ------------------------------------------------------------------
    //  View
    // ------------------------------------------------------------------

    /**
     * @notice Returns the full results array.
     */
    function getResults() external view returns (uint256[] memory) {
        uint256[] memory result = new uint256[](optionsCount);
        for (uint8 i = 0; i < optionsCount; i++) {
            result[i] = votes[i];
        }
        return result;
    }

    /**
     * @notice Returns whether the poll is currently accepting votes.
     */
    function isActive() external view returns (bool) {
        return (
            state == State.Active &&
            block.timestamp >= startTime &&
            block.timestamp <= endTime
        );
    }
}
