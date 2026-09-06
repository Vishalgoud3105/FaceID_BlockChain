"""Canonical record construction, hashing, and local storage.

This module is the tamper-evidence anchor of the whole pipeline, so its one
contract matters more than anything else here:

    the bytes hashed before the chain write must be byte-identical to the
    bytes recomputed at verification time.

To keep that true, a stored file separates the hashed payload from the chain
metadata that only exists *after* the write:

    {
      "record":      {...},   <-- hashed. never mutated after the write.
      "record_hash": "0x..",  <-- convenience copy for humans. NOT trusted.
      "chain":       {...}    <-- added post-write. deliberately not hashed.
    }

Verification recomputes sha256(canonical(file["record"])) and compares it to the
value read back from the blockchain. The file's own "record_hash" field is never
used in that comparison -- otherwise an attacker who edited the record could
simply edit the hash beside it and the check would pass.
"""
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.config import RECORDS_DIR


def canonical(payload: dict[str, Any]) -> bytes:
    """Deterministic byte encoding of a record.

    Sorted keys and no whitespace, so two structurally equal records always
    produce identical bytes regardless of how they were built or round-tripped
    through a file.
    """
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return "0x" + hashlib.sha256(data).hexdigest()


def record_hash(payload: dict[str, Any]) -> str:
    """The 32-byte digest that gets written on-chain as `recordHash`."""
    return sha256_hex(canonical(payload))


def build_record(
    *,
    image_sha256: str,
    face: dict[str, Any],
    match: dict[str, Any],
    search_meta: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the payload that will be hashed and anchored on-chain.

    Deliberately excludes the raw 512-d embedding: publishing a recoverable
    biometric vector to a permanent public ledger is irreversible. Only
    sha256(embedding) travels, inside `face`.
    """
    return {
        "schema": "hhgoa-task3/face-match/v1",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "image_sha256": image_sha256,
        "face": face,
        "match": match,
        "search": search_meta,
    }


def save(record_id: int, payload: dict[str, Any], chain: dict[str, Any]) -> str:
    """Persist a completed run. Returns the file path."""
    path = RECORDS_DIR / f"{record_id}.json"
    path.write_text(
        json.dumps(
            {
                "record": payload,
                "record_hash": record_hash(payload),
                "chain": chain,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return str(path)


def load(record_id: int) -> dict[str, Any] | None:
    path = RECORDS_DIR / f"{record_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def verify_against_chain(
    stored: dict[str, Any], onchain_record_hash: str
) -> dict[str, Any]:
    """Compare a stored record against the hash held on the blockchain.

    The local hash is RECOMPUTED from the payload, never read from the file's
    own `record_hash` field -- an attacker editing the record could edit that
    field to match.
    """
    recomputed = record_hash(stored["record"])
    ok = recomputed.lower() == onchain_record_hash.lower()
    return {
        "status": "VERIFIED" if ok else "TAMPERED",
        "recomputed_record_hash": recomputed,
        "onchain_record_hash": onchain_record_hash,
        "detail": (
            "Local record hashes to the value anchored on-chain."
            if ok
            else "Local record does NOT match the on-chain hash. It was altered "
                 "after being anchored."
        ),
    }
