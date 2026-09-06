"""CLI end-to-end run. This is the script to screen-record.

    python scripts/run_pipeline.py photo.jpg
    python scripts/run_pipeline.py photo.jpg --image-url https://example.com/photo.jpg
    python scripts/run_pipeline.py --verify 0
    python scripts/run_pipeline.py --health

It calls exactly the same pipeline the API calls -- no duplicated logic.

Responsible use: run this on your own photo, or on a public figure whose images
are already widely published. Do not use it to deanonymise a private individual.
The match URL and a hash of the face are written to a public, permanent ledger
and cannot be deleted afterwards.
"""
import argparse
import asyncio
import json
import sys
import warnings
from pathlib import Path

# insightface calls a scikit-image API that is deprecated but still correct.
# Narrowly silenced so the recorded run stays readable.
warnings.filterwarnings("ignore", category=FutureWarning, module="insightface.*")
warnings.filterwarnings("ignore", category=FutureWarning, module="skimage.*")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Windows consoles default to cp1252, which raises UnicodeEncodeError on any
# non-ASCII character in a page title or URL. Match data comes from the open
# web, so that is a matter of when, not if.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


from app import chain, config, pipeline  # noqa: E402

BAR = "=" * 72

STAGE_LABEL = {
    "input": "INPUT",
    "verify": "VERIFY",
    "face": "FACE",
    "search": "SEARCH",
    "match": "MATCH",
    "hash": "HASH",
    "chain": "CHAIN",
    "saved": "SAVED",
}


def on_stage(stage: str, message: str) -> None:
    print(f"  [{STAGE_LABEL.get(stage, stage.upper()):<6}] {message}", flush=True)


async def do_run(path: Path, image_url: str | None) -> int:
    if not path.exists():
        print(f"[error] no such file: {path}")
        return 1

    print(BAR)
    print("  FACE ID -> REVERSE IMAGE SEARCH -> BLOCKCHAIN")
    print(BAR)

    result = await pipeline.run(
        path.read_bytes(), filename=path.name, image_url=image_url, on_stage=on_stage
    )

    print(BAR)
    status = result["status"]

    if status == "no_face":
        print(f"  RESULT: NO FACE - {result['error']}")
        print(BAR)
        return 2

    if status == "image_url_mismatch":
        print("  RESULT: IMAGE URL MISMATCH")
        print(f"  {result['error']}")
        print(BAR)
        return 5

    if status == "no_social_match":
        print("  RESULT: NO SOCIAL MATCH")
        print("  The reverse-image search ran against the live web index and found")
        print("  no matching social media post. Nothing was written on-chain.")
        print("  A fabricated match would defeat the point of anchoring it.")
        print(BAR)
        return 3

    chain_info = result["chain"]
    print("  RESULT: ANCHORED ON-CHAIN")
    print(f"  match       : {result['record']['match']['url']}")
    print(f"  platform    : {result['record']['match']['host']}")
    print(f"  face hash   : {result['record']['face']['face_hash']}")
    print(f"  record hash : {result['record_hash']}")
    print(f"  chain       : {chain_info['chain_name']} (id {chain_info['chain_id']})")
    print(f"  contract    : {chain_info['contract_address']}")
    print(f"  record id   : {chain_info['record_id']}")
    print(f"  tx          : {chain_info['tx_hash']}")
    print(f"  explorer    : {chain_info['explorer_url']}")
    print(f"  saved       : {result['saved_to']}")
    print(BAR)
    print(f"  Verify it:  python scripts/run_pipeline.py --verify {chain_info['record_id']}")
    print(BAR)
    return 0


async def do_verify(record_id: int) -> int:
    print(BAR)
    print(f"  VERIFYING RECORD #{record_id} AGAINST THE BLOCKCHAIN")
    print(BAR)

    result = await pipeline.verify(record_id)
    onchain = result["onchain"]

    print(f"  contract        : {onchain['contract_address']}")
    print(f"  anchored url    : {onchain['match_url']}")
    print(f"  on-chain hash   : {result.get('onchain_record_hash', onchain['record_hash'])}")
    print(f"  recomputed hash : {result.get('recomputed_record_hash', '(no local record)')}")
    print(BAR)
    print(f"  STATUS: {result['status']}")
    print(f"  {result['detail']}")
    print(BAR)
    return 0 if result["status"] == "VERIFIED" else 4


def do_health() -> int:
    print(BAR)
    print("  HEALTH")
    print(BAR)
    print(json.dumps({
        "missing_config": config.missing_keys(),
        "search_provider": {
            "serpapi_google_lens": bool(config.SERPAPI_KEY),
        },
        "chain": chain.status(),
    }, indent=2))
    print(BAR)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Face ID -> reverse image search -> blockchain anchor."
    )
    ap.add_argument("image", nargs="?", type=Path, help="path to the input photo")
    ap.add_argument(
        "--image-url",
        default=None,
        help="REQUIRED for a run: public URL of this same image (Google Lens "
             "cannot search local bytes)",
    )
    ap.add_argument("--verify", type=int, metavar="ID", help="verify an anchored record")
    ap.add_argument("--health", action="store_true", help="show config and chain status")
    args = ap.parse_args()

    if args.health:
        return do_health()
    if args.verify is not None:
        return asyncio.run(do_verify(args.verify))
    if args.image is None:
        ap.print_help()
        return 1
    if not args.image_url:
        print("[error] --image-url is required.")
        print("")
        print("  Google Lens can only search a publicly reachable URL, and this")
        print("  pipeline deliberately never uploads your photo anywhere.")
        print("  Pass the URL where this same image is already published:")
        print("")
        print(f"    python scripts/run_pipeline.py {args.image} \\")
        print("        --image-url https://example.com/that-same-photo.jpg")
        print("")
        return 1
    return asyncio.run(do_run(args.image, args.image_url))


if __name__ == "__main__":
    raise SystemExit(main())
