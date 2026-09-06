"""Blockchain anchoring against FaceMatchRegistry on Base Sepolia.

All functions here are blocking (web3.py is synchronous), so the API layer
always calls them through run_in_executor to keep the event loop free.

Verified against web3.py 8.0.0: the signed-transaction attribute is
`raw_transaction` (snake_case). The camelCase `rawTransaction` of web3 v6 was
removed and will raise AttributeError.
"""
import json
from typing import Any

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

from app import config


class ChainError(RuntimeError):
    """Raised for any unrecoverable problem talking to the chain."""


def _artifact() -> dict[str, Any]:
    if not config.CONTRACT_ARTIFACT.exists():
        raise ChainError(
            f"contract artifact missing at {config.CONTRACT_ARTIFACT}. "
            "Run: python scripts/deploy_contract.py"
        )
    return json.loads(config.CONTRACT_ARTIFACT.read_text(encoding="utf-8"))


def get_web3() -> Web3:
    w3 = Web3(Web3.HTTPProvider(config.CHAIN_RPC_URL, request_kwargs={"timeout": 60}))
    # Base is an OP-stack chain; its extraData can exceed the 32 bytes that
    # strict Ethereum block validation expects.
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3


def get_contract(w3: Web3):
    art = _artifact()
    address = config.CONTRACT_ADDRESS or art.get("address")
    if not address:
        raise ChainError(
            "CONTRACT_ADDRESS is not set and the artifact has no address. "
            "Run: python scripts/deploy_contract.py"
        )
    return w3.eth.contract(address=Web3.to_checksum_address(address), abi=art["abi"])


def _b32(hex_str: str) -> bytes:
    """Convert an 0x-prefixed sha256 hex digest to solidity bytes32."""
    raw = Web3.to_bytes(hexstr=hex_str)
    if len(raw) != 32:
        raise ChainError(f"expected a 32-byte hash, got {len(raw)} bytes from {hex_str!r}")
    return raw


def status() -> dict[str, Any]:
    """Connectivity snapshot for /api/health. Never raises."""
    info: dict[str, Any] = {
        "chain_name": config.CHAIN_NAME,
        "rpc_url": config.CHAIN_RPC_URL,
        "chain_id_expected": config.CHAIN_ID,
        "connected": False,
    }
    try:
        w3 = get_web3()
        info["connected"] = w3.is_connected()
        if info["connected"]:
            info["chain_id_actual"] = w3.eth.chain_id
            info["block_number"] = w3.eth.block_number
        if config.WALLET_PRIVATE_KEY:
            acct = w3.eth.account.from_key(config.WALLET_PRIVATE_KEY)
            info["wallet"] = acct.address
            if info["connected"]:
                bal = w3.eth.get_balance(acct.address)
                info["balance_eth"] = float(Web3.from_wei(bal, "ether"))
                info["funded"] = bal > 0
        else:
            info["wallet"] = None
        art = _artifact()
        info["contract_address"] = config.CONTRACT_ADDRESS or art.get("address")
        if info["connected"] and info["contract_address"]:
            info["records_anchored"] = get_contract(w3).functions.total().call()
    except Exception as exc:  # health must report, not explode
        info["error"] = f"{type(exc).__name__}: {exc}"
    return info


def write_match(face_hash: str, rec_hash: str, match_url: str) -> dict[str, Any]:
    """Anchor one match on-chain. Blocking; call via run_in_executor."""
    if not config.WALLET_PRIVATE_KEY:
        raise ChainError("WALLET_PRIVATE_KEY is not set in .env")

    w3 = get_web3()
    if not w3.is_connected():
        raise ChainError(f"cannot reach RPC at {config.CHAIN_RPC_URL}")

    contract = get_contract(w3)
    account = w3.eth.account.from_key(config.WALLET_PRIVATE_KEY)

    if w3.eth.get_balance(account.address) == 0:
        raise ChainError(
            f"wallet {account.address} has zero balance on {config.CHAIN_NAME}. "
            "Fund it from a faucet before anchoring."
        )

    fn = contract.functions.recordMatch(_b32(face_hash), _b32(rec_hash), match_url)
    tx = fn.build_transaction(
        {
            "from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address),
            "chainId": config.CHAIN_ID,
            "maxFeePerGas": w3.eth.gas_price * 2,
            "maxPriorityFeePerGas": w3.eth.max_priority_fee,
        }
    )
    tx["gas"] = int(w3.eth.estimate_gas(tx) * 1.2)

    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=240)

    if receipt["status"] != 1:
        raise ChainError(f"transaction reverted: {tx_hash.hex()}")

    events = contract.events.MatchRecorded().process_receipt(receipt)
    if not events:
        raise ChainError("transaction mined but MatchRecorded event not found")
    record_id = int(events[0]["args"]["id"])

    tx_hex = tx_hash.hex()
    if not tx_hex.startswith("0x"):
        tx_hex = "0x" + tx_hex

    return {
        "record_id": record_id,
        "tx_hash": tx_hex,
        "block_number": receipt["blockNumber"],
        "gas_used": receipt["gasUsed"],
        "contract_address": contract.address,
        "chain_id": config.CHAIN_ID,
        "chain_name": config.CHAIN_NAME,
        "explorer_url": f"{config.EXPLORER_TX_URL}{tx_hex}",
        "submitter": account.address,
    }


def read_record(record_id: int) -> dict[str, Any]:
    """Read an anchored record straight off the chain.

    Needs no private key -- anyone can independently run this against the public
    RPC to verify a published record.
    """
    w3 = get_web3()
    if not w3.is_connected():
        raise ChainError(f"cannot reach RPC at {config.CHAIN_RPC_URL}")

    contract = get_contract(w3)
    total = contract.functions.total().call()
    if record_id < 0 or record_id >= total:
        raise ChainError(f"record {record_id} does not exist (chain holds {total})")

    r = contract.functions.getRecord(record_id).call()
    face_hash, rec_hash, match_url, timestamp, submitter = r
    return {
        "record_id": record_id,
        "face_hash": "0x" + face_hash.hex().removeprefix("0x"),
        "record_hash": "0x" + rec_hash.hex().removeprefix("0x"),
        "match_url": match_url,
        "timestamp": timestamp,
        "submitter": submitter,
        "contract_address": contract.address,
        "chain_name": config.CHAIN_NAME,
    }
