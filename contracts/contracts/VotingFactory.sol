// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "./VotingPoll.sol";
import "./Whitelist.sol";

/**
 * @title VotingFactory
 * @notice Creates new VotingPoll instances and acts as the registry.
 *
 *  Only POLL_CREATOR_ROLE addresses can create polls.
 *  The factory stores an immutable reference to the Whitelist so all polls
 *  share the same set of eligible voters.
 *
 *  PollId is a monotonically increasing counter.  The same value is stored
 *  both in the factory mapping and inside the VotingPoll contract; the ZK
 *  circuit binds a proof to a specific pollId so proofs cannot be replayed
 *  across polls.
 */
contract VotingFactory is AccessControl, ReentrancyGuard {
    // ------------------------------------------------------------------
    //  Roles
    // ------------------------------------------------------------------
    bytes32 public constant POLL_CREATOR_ROLE = keccak256("POLL_CREATOR_ROLE");

    // ------------------------------------------------------------------
    //  State
    // ------------------------------------------------------------------
    Whitelist public immutable whitelist;
    address   public immutable verifier;

    uint256 public nextPollId = 1;

    /// pollId → VotingPoll address
    mapping(uint256 => address) public polls;

    /// All created poll addresses in order
    address[] public pollList;

    // ------------------------------------------------------------------
    //  Events
    // ------------------------------------------------------------------
    event PollCreated(
        uint256 indexed pollId,
        address indexed pollAddress,
        address indexed creator,
        string  title,
        uint256 startTime,
        uint256 endTime
    );

    // ------------------------------------------------------------------
    //  Constructor
    // ------------------------------------------------------------------

    /**
     * @param _whitelist  Address of the deployed Whitelist contract.
     * @param _verifier   Address of the Groth16 verifier contract.
     * @param admin       Initial admin address.
     */
    constructor(
        address _whitelist,
        address _verifier,
        address admin
    ) {
        require(_whitelist != address(0), "Factory: zero whitelist");
        require(_verifier  != address(0), "Factory: zero verifier");
        require(admin      != address(0), "Factory: zero admin");

        whitelist = Whitelist(_whitelist);
        verifier  = _verifier;

        _grantRole(DEFAULT_ADMIN_ROLE,  admin);
        _grantRole(POLL_CREATOR_ROLE,   admin);
    }

    // ------------------------------------------------------------------
    //  Create poll
    // ------------------------------------------------------------------

    /**
     * @notice Creates a new anonymous voting poll.
     *
     * @param title        Poll title.
     * @param description  Poll description or IPFS CID (ipfs://Qm...).
     * @param options      Number of voting options (2–16).
     * @param startTime    Unix timestamp when voting opens.
     * @param endTime      Unix timestamp when voting closes.
     * @return pollId      The ID assigned to the new poll.
     * @return pollAddr    The address of the deployed VotingPoll.
     */
    function createPoll(
        string calldata title,
        string calldata description,
        uint8  options,
        uint256 startTime,
        uint256 endTime
    )
        external
        onlyRole(POLL_CREATOR_ROLE)
        nonReentrant
        returns (uint256 pollId, address pollAddr)
    {
        require(bytes(title).length > 0,  "Factory: empty title");
        require(startTime < endTime,       "Factory: bad time range");
        require(
            startTime >= block.timestamp,
            "Factory: start in past"
        );

        // Snapshot the current whitelist root
        uint256 currentRoot = whitelist.root();
        require(currentRoot != 0, "Factory: empty whitelist");

        pollId = nextPollId++;

        VotingPoll poll = new VotingPoll(
            pollId,
            title,
            description,
            options,
            startTime,
            endTime,
            currentRoot,
            verifier,
            msg.sender   // poll owner = creator
        );

        pollAddr = address(poll);
        polls[pollId] = pollAddr;
        pollList.push(pollAddr);

        emit PollCreated(pollId, pollAddr, msg.sender, title, startTime, endTime);
    }

    // ------------------------------------------------------------------
    //  View
    // ------------------------------------------------------------------

    function totalPolls() external view returns (uint256) {
        return pollList.length;
    }

    /**
     * @notice Paginated list of all polls.
     * @param offset  Starting index.
     * @param limit   Maximum number to return.
     */
    function getPolls(uint256 offset, uint256 limit)
        external
        view
        returns (address[] memory result)
    {
        uint256 total = pollList.length;
        if (offset >= total) return new address[](0);

        uint256 end = offset + limit;
        if (end > total) end = total;

        result = new address[](end - offset);
        for (uint256 i = offset; i < end; i++) {
            result[i - offset] = pollList[i];
        }
    }
}
