"""Full-pipeline integration through the REAL save/load path.

The network boundaries (face model, search API, chain) are substituted so this
runs offline, but everything between them -- record construction, canonical
hashing, file write, file read, verification -- is the production code path.

This is the second verification pass on the tamper-evidence contract: pass one
(test_record.py) checks hashing in memory, which would still pass if the saved
file structure and the hashed payload had drifted apart. This one proves the
hash handed to the blockchain is reproducible from the file on disk.
"""
import asyncio
import json

import numpy as np
import pytest

from app import chain, face, pipeline, record

FAKE_MATCH_URL = "https://x.com/testuser/status/1234567890123456789"


@pytest.fixture
def wired(tmp_path, monkeypatch):
    """Substitute the three external boundaries; keep everything else real."""
    monkeypatch.setattr(record, "RECORDS_DIR", tmp_path)

    # --- face model ---
    def fake_encode(image_bytes):
        emb = np.linspace(0.1, 1.0, 512, dtype=np.float32)
        emb = emb / np.linalg.norm(emb)
        meta = {
            "face_hash": face.embedding_hash(emb),
            "embedding_dim": 512,
            "embedding_model": "insightface/buffalo_l (ArcFace)",
            "normalisation": "L2",
            "bbox": [12.5, 30.25, 210.75, 260.0],
            "det_score": 0.887421,
            "face_count": 1,
            "image_size": [800, 600],
        }
        return meta, emb

    monkeypatch.setattr(face, "encode_face", fake_encode)

    # --- reverse image search ---
    async def fake_search(image_url=None):
        return {
            "social": [
                {
                    "url": FAKE_MATCH_URL,
                    "page_title": "A post",
                    "host": "x.com",
                    "provider": "serpapi_google_lens",
                    "match_type": "google_lens/visual_matches",
                }
            ],
            "meta": {
                "providers_tried": ["serpapi_google_lens"],
                "total_results": 7,
                "social_results": 1,
                "provider_status": [],
                "best_guess": [],
                "entities": [],
            },
        }

    monkeypatch.setattr(pipeline, "find_social_match", fake_search)

    # --- chain: capture exactly what would be anchored ---
    anchored = {}

    def fake_write(face_hash, rec_hash, match_url):
        anchored["face_hash"] = face_hash
        anchored["record_hash"] = rec_hash
        anchored["match_url"] = match_url
        return {
            "record_id": 0,
            "tx_hash": "0x" + "ab" * 32,
            "block_number": 46410094,
            "gas_used": 123456,
            "contract_address": "0x" + "cd" * 20,
            "chain_id": 84532,
            "chain_name": "Base Sepolia",
            "explorer_url": "https://sepolia.basescan.org/tx/0x" + "ab" * 32,
            "submitter": "0x" + "ef" * 20,
        }

    monkeypatch.setattr(chain, "write_match", fake_write)

    def fake_read(record_id):
        return {
            "record_id": record_id,
            "face_hash": anchored["face_hash"],
            "record_hash": anchored["record_hash"],
            "match_url": anchored["match_url"],
            "timestamp": 1757030000,
            "submitter": "0x" + "ef" * 20,
            "contract_address": "0x" + "cd" * 20,
            "chain_name": "Base Sepolia",
        }

    monkeypatch.setattr(chain, "read_record", fake_read)
    return tmp_path, anchored


def test_anchored_hash_is_reproducible_from_the_saved_file(wired):
    """THE contract: sha256 of the payload on disk == the hash sent on-chain."""
    tmp_path, anchored = wired

    result = asyncio.run(pipeline.run(b"fake-image-bytes", filename="t.jpg"))
    assert result["status"] == "anchored"

    saved = json.loads((tmp_path / "0.json").read_text(encoding="utf-8"))
    recomputed = record.record_hash(saved["record"])

    assert recomputed == anchored["record_hash"], (
        "hash recomputed from the saved file does not match what was anchored"
    )
    assert result["record_hash"] == anchored["record_hash"]


def test_verify_reports_verified_for_an_untouched_record(wired):
    asyncio.run(pipeline.run(b"fake-image-bytes", filename="t.jpg"))
    out = asyncio.run(pipeline.verify(0))
    assert out["status"] == "VERIFIED"
    assert out["url_matches_chain"] is True


def test_verify_detects_a_file_tampered_on_disk(wired):
    """Edit the record file the way an attacker would, then re-verify."""
    tmp_path, _ = wired
    asyncio.run(pipeline.run(b"fake-image-bytes", filename="t.jpg"))

    path = tmp_path / "0.json"
    saved = json.loads(path.read_text(encoding="utf-8"))
    saved["record"]["match"]["url"] = "https://x.com/someoneelse/status/999"
    # Attacker also updates the sidecar hash so the file looks self-consistent.
    saved["record_hash"] = record.record_hash(saved["record"])
    path.write_text(json.dumps(saved, indent=2), encoding="utf-8")

    out = asyncio.run(pipeline.verify(0))
    assert out["status"] == "TAMPERED"
    assert out["url_matches_chain"] is False


def test_chain_metadata_is_not_part_of_the_hashed_payload(wired):
    """Chain data is added after anchoring, so it must sit outside `record`."""
    tmp_path, _ = wired
    asyncio.run(pipeline.run(b"fake-image-bytes", filename="t.jpg"))

    saved = json.loads((tmp_path / "0.json").read_text(encoding="utf-8"))
    assert "chain" in saved
    assert "tx_hash" not in json.dumps(saved["record"]), (
        "tx metadata leaked into the hashed payload; the hash could never be "
        "reproduced, since it is not known until after the write"
    )


def test_no_social_match_writes_nothing_on_chain(tmp_path, monkeypatch):
    """The honesty guarantee: no match means no anchor, no file, no invention."""
    monkeypatch.setattr(record, "RECORDS_DIR", tmp_path)

    def fake_encode(image_bytes):
        emb = np.ones(512, dtype=np.float32) / np.sqrt(512)
        return {
            "face_hash": face.embedding_hash(emb),
            "embedding_dim": 512,
            "embedding_model": "insightface/buffalo_l (ArcFace)",
            "normalisation": "L2",
            "bbox": [0.0, 0.0, 10.0, 10.0],
            "det_score": 0.9,
            "face_count": 1,
            "image_size": [100, 100],
        }, emb

    async def empty_search(image_url=None):
        return {
            "social": [],
            "meta": {
                "providers_tried": ["serpapi_google_lens"],
                "total_results": 4,
                "social_results": 0,
                "provider_status": [],
                "best_guess": [],
                "entities": [],
            },
        }

    def explode(*a, **k):
        raise AssertionError("write_match must NOT be called without a real match")

    monkeypatch.setattr(face, "encode_face", fake_encode)
    monkeypatch.setattr(pipeline, "find_social_match", empty_search)
    monkeypatch.setattr(chain, "write_match", explode)

    out = asyncio.run(pipeline.run(b"img", filename="t.jpg"))

    assert out["status"] == "no_social_match"
    assert list(tmp_path.iterdir()) == []


def test_no_face_short_circuits_before_searching(tmp_path, monkeypatch):
    """A photo with no face must not be sent to a third-party search API."""
    monkeypatch.setattr(record, "RECORDS_DIR", tmp_path)

    def no_face(image_bytes):
        raise face.FaceError("no face detected in the image")

    async def explode_search(*a, **k):
        raise AssertionError("search must not run when no face was found")

    monkeypatch.setattr(face, "encode_face", no_face)
    monkeypatch.setattr(pipeline, "find_social_match", explode_search)

    out = asyncio.run(pipeline.run(b"img", filename="t.jpg"))
    assert out["status"] == "no_face"


def test_mismatched_image_url_is_refused_before_anchoring(tmp_path, monkeypatch):
    """A --image-url showing a different person must never reach the chain.

    Otherwise the pipeline would anchor THIS face against a search performed on
    a DIFFERENT photo -- a permanently false record.
    """
    import numpy as np

    monkeypatch.setattr(record, "RECORDS_DIR", tmp_path)

    local = np.zeros(512, dtype=np.float32)
    local[0] = 1.0
    remote = np.zeros(512, dtype=np.float32)
    remote[1] = 1.0  # orthogonal -> cosine similarity 0.0

    calls = {"n": 0}

    def fake_encode(image_bytes):
        calls["n"] += 1
        emb = local if calls["n"] == 1 else remote
        return {
            "face_hash": face.embedding_hash(emb),
            "embedding_dim": 512,
            "embedding_model": "insightface/buffalo_l (ArcFace)",
            "normalisation": "L2",
            "bbox": [0.0, 0.0, 10.0, 10.0],
            "det_score": 0.9,
            "face_count": 1,
            "image_size": [100, 100],
        }, emb

    class FakeResp:
        content = b"remote-image-bytes"

        def raise_for_status(self):
            pass

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            return FakeResp()

    def explode(*a, **k):
        raise AssertionError("chain must not be reached on a URL mismatch")

    async def explode_search(*a, **k):
        raise AssertionError("search must not run on a URL mismatch")

    monkeypatch.setattr(face, "encode_face", fake_encode)
    monkeypatch.setattr(pipeline.httpx, "AsyncClient", lambda **kw: FakeClient())
    monkeypatch.setattr(pipeline, "find_social_match", explode_search)
    monkeypatch.setattr(chain, "write_match", explode)

    out = asyncio.run(
        pipeline.run(b"local", filename="t.jpg", image_url="https://example.com/other.jpg")
    )

    assert out["status"] == "image_url_mismatch"
    assert out["url_check"]["verified"] is False
    assert list(tmp_path.iterdir()) == []
