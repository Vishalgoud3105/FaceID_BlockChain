"""Compile and deploy FaceMatchRegistry. Run ONCE, then paste the address into .env.

    python scripts/deploy_contract.py            # compile + deploy
    python scripts/deploy_contract.py --compile-only

The compiled ABI + address are written to contracts/FaceMatchRegistry.json and
committed, so anyone reproducing a run never needs solc installed at all.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import solcx.install as solcx_install

# py-solc-x 2.0.3 still points at solc-bin.ethereum.org, which was retired and
# no longer resolves. The current official host is binaries.soliditylang.org.
# Patch before importing anything that triggers a download.
solcx_install.BINARY_DOWNLOAD_BASE = "https://binaries.soliditylang.org/{}-amd64/{}"

import solcx  # noqa: E402
from web3 import Web3  # noqa: E402
from web3.middleware import ExtraDataToPOAMiddleware  # noqa: E402

from app import config  # noqa: E402


def compile_contract() -> tuple[list, str]:
    if config.SOLC_VERSION not in [str(v) for v in solcx.get_installed_solc_versions()]:
        print(f"[1/3] installing solc {config.SOLC_VERSION} ...")
        solcx.install_solc(config.SOLC_VERSION)

    print(f"[1/3] compiling {config.CONTRACT_SOURCE.name} with solc {config.SOLC_VERSION} ...")
    compiled = solcx.compile_files(
        [str(config.CONTRACT_SOURCE)],
        output_values=["abi", "bin"],
        solc_version=config.SOLC_VERSION,
        optimize=True,
    )
    key = next(k for k in compiled if k.endswith(":FaceMatchRegistry"))
    abi, bytecode = compiled[key]["abi"], compiled[key]["bin"]
    print(f"      ok - {len(bytecode) // 2} bytes of bytecode")
    return abi, bytecode


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compile-only", action="store_true", help="compile without deploying")
    args = ap.parse_args()

    abi, bytecode = compile_contract()

    if args.compile_only:
        config.CONTRACT_ARTIFACT.write_text(
            json.dumps({"abi": abi, "bytecode": bytecode, "address": None}, indent=2),
            encoding="utf-8",
        )
        print(f"[done] artifact -> {config.CONTRACT_ARTIFACT}")
        return 0

    if not config.WALLET_PRIVATE_KEY:
        print("\n[error] WALLET_PRIVATE_KEY is not set in .env - cannot deploy.")
        print("        Fund a throwaway wallet at https://www.alchemy.com/faucets/base-sepolia")
        return 1

    print(f"[2/3] connecting to {config.CHAIN_NAME} ({config.CHAIN_RPC_URL}) ...")
    w3 = Web3(Web3.HTTPProvider(config.CHAIN_RPC_URL))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    if not w3.is_connected():
        print("[error] cannot reach the RPC endpoint.")
        return 1

    account = w3.eth.account.from_key(config.WALLET_PRIVATE_KEY)
    balance = w3.eth.get_balance(account.address)
    print(f"      chain id {w3.eth.chain_id}, block {w3.eth.block_number}")
    print(f"      deployer {account.address}  balance {w3.from_wei(balance, 'ether')} ETH")
    if balance == 0:
        print("\n[error] deployer has 0 balance. Fund it from a Base Sepolia faucet first.")
        return 1

    print("[3/3] deploying ...")
    contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    tx = contract.constructor().build_transaction(
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
    print(f"      tx 0x{tx_hash.hex().removeprefix(chr(48)+chr(120))} - waiting for receipt ...")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)

    # HexBytes.hex() drops the 0x prefix on current hexbytes releases.
    tx_hex = tx_hash.hex()
    if not tx_hex.startswith("0x"):
        tx_hex = "0x" + tx_hex

    if receipt.status != 1:
        print("[error] deployment transaction reverted.")
        return 1

    address = receipt.contractAddress
    config.CONTRACT_ARTIFACT.write_text(
        json.dumps(
            {
                "abi": abi,
                "bytecode": bytecode,
                "address": address,
                "chain_id": config.CHAIN_ID,
                "chain_name": config.CHAIN_NAME,
                "deploy_tx": tx_hex,
                "deploy_block": receipt.blockNumber,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\n" + "=" * 68)
    print(f"  DEPLOYED to {config.CHAIN_NAME}")
    print(f"  address : {address}")
    print(f"  tx      : {config.EXPLORER_TX_URL}{tx_hex}")
    print(f"  artifact: {config.CONTRACT_ARTIFACT}")
    print("=" * 68)
    print(f"\n  Add this line to your .env:\n\n      CONTRACT_ADDRESS={address}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
