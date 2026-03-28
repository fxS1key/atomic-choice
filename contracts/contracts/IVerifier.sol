// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title IVerifier
 * @notice Interface for the Groth16 verifier contract that is auto-generated
 *         by snarkJS from the compiled Circom circuit.
 *
 *  Generation steps (offline):
 *    1. Write circuit:   circuits/vote.circom
 *    2. Compile:         circom vote.circom --r1cs --wasm --sym
 *    3. Powers of Tau:   snarkjs powersoftau new bn128 16 pot16_0000.ptau
 *                        snarkjs powersoftau contribute pot16_0000.ptau pot16_0001.ptau
 *                        snarkjs powersoftau prepare phase2 pot16_0001.ptau pot16_final.ptau
 *    4. Circuit setup:   snarkjs groth16 setup vote.r1cs pot16_final.ptau vote_0000.zkey
 *                        snarkjs zkey contribute vote_0000.zkey vote_0001.zkey
 *                        snarkjs zkey export verificationkey vote_0001.zkey verification_key.json
 *    5. Export verifier: snarkjs zkey export solidityverifier vote_0001.zkey Verifier.sol
 *
 *  The exported Verifier.sol will implement this interface.
 */
interface IVerifier {
    /**
     * @notice Verifies a Groth16 proof.
     * @param _pA   Proof point A  [2]
     * @param _pB   Proof point B  [2][2]
     * @param _pC   Proof point C  [2]
     * @param _pubSignals  Public signals (nullifierHash, root, vote, pollId)
     * @return bool  True if the proof is valid.
     */
    function verifyProof(
        uint256[2]    calldata _pA,
        uint256[2][2] calldata _pB,
        uint256[2]    calldata _pC,
        uint256[4]    calldata _pubSignals
    ) external view returns (bool);
}
