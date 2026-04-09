import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

try:
    from web3 import Web3
    from web3.middleware import geth_poa_middleware
except ImportError:  # pragma: no cover - optional dependency
    Web3 = None  # type: ignore

LOGGER = logging.getLogger("pharmaledger.chain")
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_ABI_PATH = BASE_DIR / "chain" / "artifacts" / "contracts" / "PharmaLedger.sol" / "PharmaLedger.json"


class ChainClient:
    """Best-effort Ethereum helper with a mock fallback when keys are missing."""

    def __init__(self) -> None:
        self.rpc_url = os.getenv("CHAIN_RPC_URL")
        self.private_key = os.getenv("CHAIN_PRIVATE_KEY")
        self.contract_address = os.getenv("CHAIN_CONTRACT_ADDRESS")
        abi_hint = os.getenv("CHAIN_ABI_PATH")
        self.abi_path = Path(abi_hint) if abi_hint else DEFAULT_ABI_PATH

        self.web3 = None
        self.contract = None
        self.account = None
        self.mode = "disabled"
        self.mock_path = BASE_DIR / "mock_chain.json"

        self._bootstrap()
        if self.mode == "disabled":
            self._init_mock()

    # ------------------------------------------------------------------
    def _bootstrap(self) -> None:
        if Web3 is None:
            LOGGER.info("web3.py not installed; blockchain bridge disabled.")
            return
        if not (self.rpc_url and self.private_key and self.contract_address):
            LOGGER.info("CHAIN_* variables not set; blockchain bridge disabled.")
            return
        if not self.abi_path.exists():
            LOGGER.info("Contract ABI not found at %s; blockchain bridge disabled.", self.abi_path)
            return

        abi_data = json.loads(self.abi_path.read_text())
        abi = abi_data.get("abi", abi_data)

        self.web3 = Web3(Web3.HTTPProvider(self.rpc_url))
        if os.getenv("CHAIN_USE_POA", "1") == "1":
            self.web3.middleware_onion.inject(geth_poa_middleware, layer=0)

        self.account = self.web3.eth.account.from_key(self.private_key)
        checksum = Web3.to_checksum_address(self.contract_address)
        self.contract = self.web3.eth.contract(address=checksum, abi=abi)
        self.mode = "real"
        LOGGER.info("Blockchain bridge ready for account %s", self.account.address)

    # ------------------------------------------------------------------
    @property
    def enabled(self) -> bool:
        return self.mode in {"real", "mock"}

    # ------------------------------------------------------------------
    def _init_mock(self) -> None:
        if not self.mock_path.exists():
            self.mock_path.write_text(json.dumps({}))
        self.mode = "mock"
        LOGGER.info("Blockchain bridge running in mock mode (file %s)", self.mock_path)

    # ------------------------------------------------------------------
    def _load_mock(self) -> Dict[str, List[dict]]:
        try:
            return json.loads(self.mock_path.read_text())
        except Exception:
            return {}

    # ------------------------------------------------------------------
    def _store_mock(self, data: Dict[str, List[dict]]) -> None:
        self.mock_path.write_text(json.dumps(data, indent=2))

    # ------------------------------------------------------------------
    def _mock_append(self, uid: str, event: str, location: str, prev_hash: str, curr_hash: str):
        store = self._load_mock()
        entries = store.setdefault(uid, [])
        entries.append(
            {
                "event": event,
                "location": location,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "prev_hash": prev_hash,
                "curr_hash": curr_hash,
            }
        )
        self._store_mock(store)
        return f"mock-{len(entries)}"

    # ------------------------------------------------------------------
    def _transact(self, func):
        if self.mode != "real":
            return None
        assert self.web3 is not None and self.account is not None

        nonce = self.web3.eth.get_transaction_count(self.account.address)
        gas_price = self.web3.eth.gas_price
        tx = func.build_transaction(
            {
                "from": self.account.address,
                "nonce": nonce,
                "gas": 500_000,
                "gasPrice": gas_price,
                "chainId": self.web3.eth.chain_id,
            }
        )
        try:
            signed = self.web3.eth.account.sign_transaction(tx, private_key=self.account.key)
            tx_hash = self.web3.eth.send_raw_transaction(signed.rawTransaction)
            receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash)
            LOGGER.info("On-chain tx %s confirmed in block %s", tx_hash.hex(), receipt.blockNumber)
            return tx_hash.hex()
        except Exception as exc:  # pragma: no cover - depends on network
            LOGGER.warning("Blockchain tx failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    def register_drug(self, uid: str, name: str, batch: str, quantity: int):
        if self.mode == "real":
            func = self.contract.functions.registerDrug(uid, name, batch, int(quantity))
            return self._transact(func)
        prev_hash = "GENESIS"
        curr_hash = f"REGISTERED::{uid}"
        return self._mock_append(uid, "REGISTERED", "Manufacturing Portal", prev_hash, curr_hash)

    # ------------------------------------------------------------------
    def append_event(self, uid: str, event: str, location: str, prev_hash: str, curr_hash: str):
        if self.mode == "real":
            func = self.contract.functions.appendEvent(uid, event, location, prev_hash, curr_hash)
            return self._transact(func)
        return self._mock_append(uid, event, location, prev_hash, curr_hash)

    # ------------------------------------------------------------------
    def list_events(self, uid: str):
        if self.mode == "real":
            entries = self.contract.functions.getEvents(uid).call()
            result = []
            for item in entries:
                result.append(
                    {
                        "event": item[0],
                        "location": item[1],
                        "timestamp": datetime.utcfromtimestamp(int(item[2])).isoformat() + "Z",
                        "prev_hash": item[3],
                        "curr_hash": item[4],
                    }
                )
            return result
        store = self._load_mock()
        return store.get(uid, [])


chain = ChainClient()
