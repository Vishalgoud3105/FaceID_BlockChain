// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title FaceMatchRegistry
/// @notice Append-only, tamper-evident anchor for face-to-social-post matches.
///
/// @dev Design notes:
///  - Records are append-only. There is no update or delete function, by
///    design: an anchor you can rewrite is not an anchor.
///  - No raw biometric data is ever stored here. `faceHash` is sha256 of an
///    L2-normalised face embedding; the embedding itself never leaves the
///    machine that produced it and cannot be recovered from the hash.
///  - `recordHash` is sha256 of the canonical JSON of the full match record.
///    Anyone can re-hash the published record and compare it against this
///    value to detect post-hoc alteration.
///  - Permissionless on purpose. Access control would imply this registry
///    asserts that a match is *true*; it does not. It only proves a specific
///    claim existed, unmodified, at a specific block.
contract FaceMatchRegistry {
    struct Record {
        bytes32 faceHash;   // sha256(L2-normalised 512-d embedding)
        bytes32 recordHash; // sha256(canonical JSON of the match record)
        string  matchUrl;   // the social media post that was matched
        uint256 timestamp;  // block time of anchoring
        address submitter;  // who anchored it
    }

    Record[] public records;

    event MatchRecorded(
        uint256 indexed id,
        bytes32 indexed faceHash,
        bytes32 recordHash,
        string  matchUrl,
        address indexed submitter,
        uint256 timestamp
    );

    error EmptyHash();
    error EmptyUrl();

    /// @notice Anchor one face-to-post match.
    /// @return id Index of the new record, also emitted in MatchRecorded.
    function recordMatch(
        bytes32 faceHash,
        bytes32 recordHash,
        string calldata matchUrl
    ) external returns (uint256 id) {
        if (faceHash == bytes32(0) || recordHash == bytes32(0)) revert EmptyHash();
        if (bytes(matchUrl).length == 0) revert EmptyUrl();

        id = records.length;
        records.push(
            Record({
                faceHash:   faceHash,
                recordHash: recordHash,
                matchUrl:   matchUrl,
                timestamp:  block.timestamp,
                submitter:  msg.sender
            })
        );

        emit MatchRecorded(id, faceHash, recordHash, matchUrl, msg.sender, block.timestamp);
    }

    /// @notice Number of anchored records.
    function total() external view returns (uint256) {
        return records.length;
    }

    /// @notice Full record as a struct (the public array getter flattens it).
    function getRecord(uint256 id) external view returns (Record memory) {
        return records[id];
    }
}
