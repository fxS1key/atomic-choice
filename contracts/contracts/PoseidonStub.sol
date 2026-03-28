// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./PoseidonT3.sol";

/**
 * @title PoseidonStub
 * @notice TEST-ONLY keccak-based stub that implements IPoseidonT3.
 *         Replace with the real Poseidon contract from circomlibjs in production.
 */
contract PoseidonStub is IPoseidonT3 {
    uint256 constant SNARK_SCALAR_FIELD =
        21888242871839275222246405745257275088548364400416034343698204186575808495617;

    function poseidon(uint256[2] memory inputs)
        external
        pure
        override
        returns (uint256)
    {
        return uint256(keccak256(abi.encodePacked(inputs[0], inputs[1]))) %
            SNARK_SCALAR_FIELD;
    }
}
