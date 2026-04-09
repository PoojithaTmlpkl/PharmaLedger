// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract PharmaLedger {
    address public admin;

    struct DrugBatch {
        string uid;
        string name;
        string batchId;
        uint256 quantity;
        address manufacturer;
        bool exists;
    }

    struct EventEntry {
        string eventType;
        string location;
        uint256 timestamp;
        string prevHash;
        string currHash;
    }

    mapping(string => DrugBatch) private drugs;
    mapping(string => EventEntry[]) private ledger;

    event DrugRegistered(string indexed uid, string name, string batchId, uint256 quantity, address manufacturer);
    event LedgerEvent(
        string indexed uid,
        string eventType,
        string location,
        string prevHash,
        string currHash,
        uint256 timestamp
    );

    modifier onlyAdmin() {
        require(msg.sender == admin, "Not authorized");
        _;
    }

    constructor() {
        admin = msg.sender;
    }

    function registerDrug(
        string calldata uid,
        string calldata name,
        string calldata batchId,
        uint256 quantity
    ) external onlyAdmin {
        require(!drugs[uid].exists, "Already registered");
        drugs[uid] = DrugBatch(uid, name, batchId, quantity, msg.sender, true);
        emit DrugRegistered(uid, name, batchId, quantity, msg.sender);
    }

    function appendEvent(
        string calldata uid,
        string calldata eventType,
        string calldata location,
        string calldata prevHash,
        string calldata currHash
    ) external onlyAdmin {
        require(drugs[uid].exists, "Unknown UID");
        EventEntry memory entry = EventEntry(eventType, location, block.timestamp, prevHash, currHash);
        ledger[uid].push(entry);
        emit LedgerEvent(uid, eventType, location, prevHash, currHash, block.timestamp);
    }

    function getDrug(string calldata uid) external view returns (DrugBatch memory) {
        require(drugs[uid].exists, "Unknown UID");
        return drugs[uid];
    }

    function getEvents(string calldata uid) external view returns (EventEntry[] memory) {
        return ledger[uid];
    }
}
