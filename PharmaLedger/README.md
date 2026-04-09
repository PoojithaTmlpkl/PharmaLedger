# PharmaLedger

End-to-end drug traceability platform built with Flask, SQLite, QR serialization, and optional Ethereum anchoring through a dedicated smart contract.

## Features

- Role-based dashboards for manufacturers, distributors, hospitals, and regulators.
- QR code generation + scanning for every drug batch.
- Immutable audit trail stored locally and (optionally) on Ethereum via the `PharmaLedger` smart contract.
- Admin analytics with multi-chart visualizations.

## Tracking workflow (3-party hop)

1. **Manufacturer ➜ Distributor**: The manufacturer dashboard creates the batch, prints/embeds the QR label, and transfers custody to a distributor. The transfer logs in SQLite (and on-chain if blockchain mode is enabled) together with a tamper-proof hash of the payload.
2. **Distributor ➜ Hospital/Pharmacy**: The distributor signs in, scans the QR using the `transfer` or `receive` pages, and records temperature/lot metadata before sending the batch onward. Every scan rehydrates history so discrepancies are visible immediately.
3. **Delivery confirmation**: The receiving hospital/pharmacy scans the QR via the `receive` view to confirm delivery. Regulators can head to the `verify` page, scan the same QR, and review the full hop-by-hop timeline.

QR scans work from any camera-equipped device pointed at the Flask `/scan` endpoint; no browser extension is required. MetaMask (or any wallet) is only needed if you want to manually interact with the deployed smart contract—PharmaLedger signs blockchain writes with the `PRIVATE_KEY` configured in `.env`, so normal users just use the web app.

## Running the Flask app

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Visit `http://127.0.0.1:5000` and register/login to start onboarding batches.

## Enabling blockchain mode

The repository now ships with a Solidity contract (`chain/contracts/PharmaLedger.sol`) and a Hardhat workspace under `chain/`.

1. **Install dependencies**
   ```bash
   cd chain
   npm install
   ```
2. **Configure environment**
   Copy `chain/.env.example` to `chain/.env` and set `RPC_URL`, `PRIVATE_KEY`, and (optionally) `ETHERSCAN_KEY`.
3. **Deploy the contract**
   ```bash
   npx hardhat compile
   npx hardhat run scripts/deploy.js --network sepolia   # or localhost
   ```
   Note the contract address from the output.
4. **Expose settings to Flask**
   Create a `.env` (or set real env vars) at the project root with:
   ```ini
   CHAIN_RPC_URL=https://...
   CHAIN_PRIVATE_KEY=0x...
   CHAIN_CONTRACT_ADDRESS=0x...
   CHAIN_ABI_PATH=chain/artifacts/contracts/PharmaLedger.sol/PharmaLedger.json
   ```
5. **Install Python web3**
   ```bash
   pip install web3
   ```

With these variables set, every new batch registration and ledger event will also be written to the smart contract. The verification screen shows both local and on-chain timelines.

## Notes

- The smart contract restricts writes to the deploying admin account. Use multisig / role management as needed.
- If blockchain settings are missing, the app silently falls back to the local hash chain.
- For PoA testnets (e.g., Sepolia, Polygon), the client injects the POA middleware automatically.
