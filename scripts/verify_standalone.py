"""Independent verification. Imports NOTHING from this project.

For anyone who wants to check an anchored record without trusting the pipeline code:

    python scripts/verify_standalone.py 1 records/1.json

It needs no API keys, no wallet, and no .env -- only the public Base Sepolia
RPC. It reads the record hash straight off the blockchain, recomputes the hash
of the local record file, and compares them.

The contract address and ABI below are hardcoded on purpose: this script is
meant to be readable end to end and copy-pasteable, so a reviewer can satisfy
themselves that nothing is being hidden in a helper module.
"""
import hashlib
import json
import sys

# Windows consoles default to cp1252, which raises UnicodeEncodeError on any
# non-ASCII character in a page title or URL. Match data comes from the open
# web, so that is a matter of when, not if.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


from web3 import Web3

RPC_URL = "https://sepolia.base.org"
CONTRACT_ADDRESS = "0x039E7A1234DD150522cb34a44Ca16056dC2B2daD"
EXPLORER = "https://sepolia.basescan.org"

# Only the one read function is needed.
ABI = [
    {
        "inputs": [{"name": "id", "type": "uint256"}],
        "name": "getRecord",
        "outputs": [
            {
                "components": [
                    {"name": "faceHash", "type": "bytes32"},
                    {"name": "recordHash", "type": "bytes32"},
                    {"name": "matchUrl", "type": "string"},
                    {"name": "timestamp", "type": "uint256"},
                    {"name": "submitter", "type": "address"},
                ],
                "name": "",
                "type": "tuple",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "total",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]


def canonical(payload: dict) -> bytes:
    """Must match app/record.py exactly: sorted keys, no whitespace, ASCII."""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        print("usage: python scripts/verify_standalone.py <record_id> <path/to/record.json>")
        return 1

    record_id = int(sys.argv[1])
    path = sys.argv[2]

    print("=" * 72)
    print("  INDEPENDENT VERIFICATION (no keys, no wallet, public RPC only)")
    print("=" * 72)

    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    if not w3.is_connected():
        print(f"[error] cannot reach {RPC_URL}")
        return 1

    contract = w3.eth.contract(
        address=Web3.to_checksum_address(CONTRACT_ADDRESS), abi=ABI
    )

    total = contract.functions.total().call()
    if record_id >= total:
        print(f"[error] record {record_id} does not exist (chain holds {total})")
        return 1

    face_hash, rec_hash, match_url, timestamp, submitter = contract.functions.getRecord(
        record_id
    ).call()
    onchain_hash = "0x" + rec_hash.hex().removeprefix("0x")

    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)["record"]
    local_hash = "0x" + hashlib.sha256(canonical(payload)).hexdigest()

    print(f"  chain           : Base Sepolia (84532), block {w3.eth.block_number}")
    print(f"  contract        : {CONTRACT_ADDRESS}")
    print(f"  records anchored: {total}")
    print("-" * 72)
    print(f"  record id       : {record_id}")
    print(f"  anchored url    : {match_url}")
    print(f"  face hash       : 0x{face_hash.hex().removeprefix('0x')}")
    print(f"  anchored at     : block timestamp {timestamp}")
    print(f"  submitted by    : {submitter}")
    print("-" * 72)
    print(f"  hash ON-CHAIN   : {onchain_hash}")
    print(f"  hash RECOMPUTED : {local_hash}")
    print("=" * 72)

    if onchain_hash.lower() == local_hash.lower():
        print("  RESULT: VERIFIED")
        print("  The local record file hashes to exactly the value anchored")
        print("  on-chain. It has not been altered since it was recorded.")
        ok = True
    else:
        print("  RESULT: TAMPERED")
        print("  The local record does NOT hash to the on-chain value. It was")
        print("  modified after being anchored.")
        ok = False

    print("=" * 72)
    print(f"  Inspect on the explorer:")
    print(f"    {EXPLORER}/address/{CONTRACT_ADDRESS}")
    print("=" * 72)
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
