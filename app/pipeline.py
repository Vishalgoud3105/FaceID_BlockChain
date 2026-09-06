"""End-to-end orchestration: photo -> face encoding -> reverse search -> chain.

Both the HTTP API and the CLI call `run()`. There is deliberately no second copy
of this sequence anywhere, so what gets screen-recorded on the CLI is exactly
what the API executes.
"""
import asyncio
import hashlib

import httpx
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from app import chain, face, record
from app.reverse_search import find_social_match

# Two workers: ONNX inference and the chain round-trip are both blocking, and
# neither benefits from more parallelism on a single-request pipeline.
executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="faceid")

# Cosine similarity floor for accepting that --image-url is the same face.
# ArcFace: same person typically 0.7-0.95; the same *image* re-encoded sits
# near 1.0, so 0.9 accepts CDN re-encoding while rejecting a different person.
URL_MATCH_THRESHOLD = 0.9

StageFn = Callable[[str, str], None]


def _noop(stage: str, message: str) -> None:
    pass


async def run(
    image_bytes: bytes,
    *,
    filename: str = "upload",
    image_url: str | None = None,
    on_stage: StageFn = _noop,
) -> dict[str, Any]:
    """Run the full pipeline.

    Returns a dict whose `status` is one of:
      no_face          - no usable face in the photo, nothing searched
      no_social_match  - search ran genuinely and found no social post; NOTHING
                         is written on-chain. This is a valid outcome, not an
                         error to be papered over with a fabricated match.
      anchored         - match found and anchored on-chain
    """
    loop = asyncio.get_running_loop()

    image_sha256 = "0x" + hashlib.sha256(image_bytes).hexdigest()
    on_stage("input", f"{filename} ({len(image_bytes):,} bytes) sha256={image_sha256[:18]}...")

    # --- 1. detect + encode ------------------------------------------------
    on_stage("face", "detecting and encoding face (InsightFace buffalo_l)...")
    try:
        face_meta, _embedding = await loop.run_in_executor(
            executor, face.encode_face, image_bytes
        )
    except face.FaceError as exc:
        on_stage("face", f"FAILED: {exc}")
        return {"status": "no_face", "error": str(exc), "image_sha256": image_sha256}

    on_stage(
        "face",
        f"face {face_meta['face_count']} found, det_score={face_meta['det_score']}, "
        f"{face_meta['embedding_dim']}-d embedding, face_hash={face_meta['face_hash'][:18]}...",
    )

    # --- 1b. confirm image_url really is this same image ---------------------
    # Without this, a mismatched --image-url would anchor THIS face against a
    # search result for a DIFFERENT photo -- a false record, permanently.
    url_check: dict[str, Any] = {"supplied": image_url is not None}
    if image_url:
        on_stage("verify", f"confirming {image_url[:60]}... is the same image")
        try:
            async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
                resp = await client.get(image_url)
            resp.raise_for_status()
            remote_meta, remote_emb = await loop.run_in_executor(
                executor, face.encode_face, resp.content
            )
            similarity = float(np.dot(_embedding, remote_emb))
            url_check.update(
                {"fetched": True, "similarity": round(similarity, 4),
                 "verified": similarity >= URL_MATCH_THRESHOLD}
            )
            if similarity < URL_MATCH_THRESHOLD:
                on_stage(
                    "verify",
                    f"REJECTED: face similarity {similarity:.3f} < {URL_MATCH_THRESHOLD}. "
                    "The URL points at a different person or photo.",
                )
                return {
                    "status": "image_url_mismatch",
                    "error": (
                        f"--image-url does not match the input photo "
                        f"(face similarity {similarity:.3f}). Refusing to anchor a "
                        "record that would bind this face to another image's search."
                    ),
                    "image_sha256": image_sha256,
                    "face": face_meta,
                    "url_check": url_check,
                }
            on_stage("verify", f"same image confirmed (face similarity {similarity:.3f})")
        except Exception as exc:
            # Some hosts block automated fetches. Proceed, but record honestly
            # that the link could not be independently confirmed.
            url_check.update({"fetched": False, "verified": None,
                              "reason": f"{type(exc).__name__}: {exc}"[:200]})
            on_stage("verify", f"could not fetch URL to confirm ({type(exc).__name__}); "
                               "recording it as unverified")

    # --- 2. genuine reverse image search -----------------------------------
    on_stage("search", "querying Google Lens (SerpApi) against the live web index...")
    search = await find_social_match(image_url)
    meta = search["meta"]
    on_stage(
        "search",
        f"{meta['total_results']} total results, {meta['social_results']} on social platforms "
        f"(providers: {', '.join(meta['providers_tried'])})",
    )
    for p in meta["provider_status"]:
        if not p["available"]:
            on_stage("search", f"  {p['provider']}: unavailable - {p['reason']}")

    if not search["social"]:
        on_stage("search", "no social media match found - nothing will be written on-chain")
        return {
            "status": "no_social_match",
            "image_sha256": image_sha256,
            "face": face_meta,
            "search": meta,
        }

    best = search["social"][0]
    on_stage("match", f"{best['host']} -> {best['url']}")

    # --- 3. build + hash the record ----------------------------------------
    payload = record.build_record(
        image_sha256=image_sha256,
        face=face_meta,
        match={
            "url": best["url"],
            "page_title": best.get("page_title", ""),
            "host": best["host"],
            "provider": best["provider"],
            "match_type": best.get("match_type", ""),
        },
        search_meta={
            "providers_tried": meta["providers_tried"],
            "total_results": meta["total_results"],
            "social_results": meta["social_results"],
            "image_url": image_url,
            "image_url_check": url_check,
        },
    )
    rec_hash = record.record_hash(payload)
    on_stage("hash", f"record_hash={rec_hash}")

    # --- 4. anchor on-chain -------------------------------------------------
    on_stage("chain", f"anchoring on {chain.config.CHAIN_NAME}...")
    chain_result = await loop.run_in_executor(
        executor, chain.write_match, face_meta["face_hash"], rec_hash, best["url"]
    )
    on_stage(
        "chain",
        f"record #{chain_result['record_id']} in block {chain_result['block_number']} "
        f"(gas {chain_result['gas_used']:,})",
    )
    on_stage("chain", chain_result["explorer_url"])

    path = record.save(chain_result["record_id"], payload, chain_result)
    on_stage("saved", path)

    return {
        "status": "anchored",
        "record_id": chain_result["record_id"],
        "record_hash": rec_hash,
        "record": payload,
        "chain": chain_result,
        "other_social_matches": search["social"][1:6],
        "saved_to": path,
    }


async def verify(record_id: int) -> dict[str, Any]:
    """Re-derive a stored record and compare it to what the blockchain holds."""
    loop = asyncio.get_running_loop()
    onchain = await loop.run_in_executor(executor, chain.read_record, record_id)

    stored = record.load(record_id)
    if stored is None:
        return {
            "status": "NO_LOCAL_RECORD",
            "onchain": onchain,
            "detail": (
                f"Record {record_id} exists on-chain but no local copy was found. "
                "The anchor stands on its own; supply the record file to verify it."
            ),
        }

    result = record.verify_against_chain(stored, onchain["record_hash"])
    result["record_id"] = record_id
    result["onchain"] = onchain
    result["url_matches_chain"] = (
        stored["record"]["match"]["url"] == onchain["match_url"]
    )
    return result
