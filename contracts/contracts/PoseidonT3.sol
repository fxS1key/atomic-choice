// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title PoseidonT3
 * @notice Poseidon hash function for 2 inputs.
 *         This is a simplified reference implementation.
 *         In production use the auto-generated contract from circomlibjs.
 *
 *  Generation steps (offline):
 *    npm install circomlibjs
 *    node -e "
 *      const {buildPoseidon} = require('circomlibjs');
 *      buildPoseidon().then(p => {
 *        const {abi,bytecode} = require('circomlibjs').poseidonContract.generateABI(2);
 *        console.log(JSON.stringify({abi, bytecode}));
 *      })
 *    "
 *  Then deploy that bytecode and use its address.
 *
 *  This file provides the interface so contracts compile without the real deploy.
 */
library PoseidonT3 {
    /**
     * @dev Placeholder — replaced at deploy time by the real Poseidon contract call.
     *      See IPoseidonT3 interface below.
     */
    function hash(uint256[2] memory inputs) internal pure returns (uint256) {
        // NOTE: This is NOT a real Poseidon. Replace with external contract call.
        // See UniVoteDeployer.sol for how to wire the real implementation.
        return uint256(keccak256(abi.encodePacked(inputs[0], inputs[1]))) >> 8;
    }
}

/**
 * @title IPoseidonT3
 * @notice Interface for the externally-deployed Poseidon T3 contract.
 */
interface IPoseidonT3 {
    function poseidon(uint256[2] memory inputs) external pure returns (uint256);
}
