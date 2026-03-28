// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./IVerifier.sol";

/**
 * @title VerifierStub
 * @notice TEST-ONLY verifier that accepts any proof.
 *         NEVER deploy this to mainnet.
 *
 *  Replace with the snarkJS-generated Verifier.sol before production.
 */
contract VerifierStub is IVerifier {
    function verifyProof(
        uint256[2]    calldata,
        uint256[2][2] calldata,
        uint256[2]    calldata,
        uint256[4]    calldata
    ) external pure override returns (bool) {
        return true; // stub: always valid — for local testing only
    }
}
