"""Tamper-evidence checks. Fully offline -- no models, no network, no chain."""
import copy
import json

import pytest

from app import record


def _payload():
    return record.build_record(
        image_sha256="0x" + "ab" * 32,
        face={
            "bbox": [10.0, 20.0, 110.5, 140.25],
            "det_score": 0.912345,
            "face_count": 1,
            "embedding_dim": 512,
            "face_hash": "0x" + "cd" * 32,
        },
        match={
            "url": "https://x.com/someuser/status/1234567890",
            "page_title": "a real post",
            "host": "x.com",
            "provider": "serpapi_google_lens",
            "match_type": "google_lens/visual_matches",
        },
        search_meta={"total_results": 12, "social_results": 1, "providers_tried": ["serpapi_google_lens"]},
    )


def test_canonical_is_key_order_independent():
    a = {"z": 1, "a": {"y": 2, "b": 3}}
    b = {"a": {"b": 3, "y": 2}, "z": 1}
    assert record.canonical(a) == record.canonical(b)
    assert record.record_hash(a) == record.record_hash(b)


def test_hash_is_stable_across_json_round_trip():
    """A record read back off disk must hash identically to the original.

    This is the property the whole verification path rests on: floats, unicode
    and nesting all have to survive save -> load unchanged.
    """
    p = _payload()
    before = record.record_hash(p)
    after = record.record_hash(json.loads(json.dumps(p, indent=2)))
    assert before == after


def test_hash_is_32_bytes():
    """recordHash is written to a solidity bytes32 -- it must fit exactly."""
    h = record.record_hash(_payload())
    assert h.startswith("0x")
    assert len(bytes.fromhex(h[2:])) == 32


@pytest.mark.parametrize(
    "path",
    [
        ("match", "url"),
        ("match", "host"),
        ("match", "page_title"),
        ("face", "face_hash"),
        ("face", "det_score"),
        ("image_sha256",),
    ],
)
def test_any_mutation_changes_the_hash(path):
    """Editing any field of an anchored record must break its hash."""
    original = _payload()
    baseline = record.record_hash(original)

    tampered = copy.deepcopy(original)
    target = tampered
    for key in path[:-1]:
        target = target[key]
    current = target[path[-1]]
    target[path[-1]] = current + "_x" if isinstance(current, str) else current + 1

    assert record.record_hash(tampered) != baseline


def test_verify_detects_tampering():
    original = _payload()
    anchored = record.record_hash(original)

    good = record.verify_against_chain({"record": original}, anchored)
    assert good["status"] == "VERIFIED"

    tampered = copy.deepcopy(original)
    tampered["match"]["url"] = "https://x.com/someuser/status/9999999999"
    bad = record.verify_against_chain({"record": tampered}, anchored)
    assert bad["status"] == "TAMPERED"


def test_verify_ignores_the_files_own_hash_field():
    """The attack this guards against: edit the record AND its hash field.

    Verification must compare against the chain, so forging the sidecar field
    changes nothing.
    """
    original = _payload()
    anchored = record.record_hash(original)

    tampered = copy.deepcopy(original)
    tampered["match"]["url"] = "https://x.com/attacker/status/1"
    forged_file = {
        "record": tampered,
        "record_hash": record.record_hash(tampered),  # attacker recomputes it
    }

    result = record.verify_against_chain(forged_file, anchored)
    assert result["status"] == "TAMPERED"


def test_embedding_never_enters_the_record():
    """Only the hash of the embedding may be published, never the vector."""
    blob = json.dumps(_payload())
    assert "embedding" not in json.loads(blob)["face"]
    assert "face_hash" in json.loads(blob)["face"]


def test_placeholder_env_values_are_treated_as_unset(monkeypatch):
    """Copying .env.example to .env must not look like a configured key."""
    from app.config import _env

    monkeypatch.setenv("X_TEST_KEY", "your_serpapi_key")
    assert _env("X_TEST_KEY") == ""

    monkeypatch.setenv("X_TEST_KEY", "0xyour_testnet_private_key")
    assert _env("X_TEST_KEY") == ""

    monkeypatch.setenv("X_TEST_KEY", "AIzaSyRealLookingKey123")
    assert _env("X_TEST_KEY") == "AIzaSyRealLookingKey123"
