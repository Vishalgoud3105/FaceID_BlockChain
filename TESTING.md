# Tests & Verification Evidence

**Face ID → Reverse Image Search → Blockchain**

Two kinds of evidence live here:

1. The automated test suite: 41 tests, fully offline, needing no network or models
2. Live verification runs: real output from the deployed contract on Base Sepolia

Everything below was executed. Every output is copied verbatim.

---

## Running the tests

```bash
cd backend
py -3.11 -m venv faceid
faceid\Scripts\activate           # Windows
# source faceid/bin/activate      # macOS / Linux
pip install -r requirements.txt

pytest -q
```

```
.........................................                                [100%]
41 passed in 1.63s
```

No API keys, no wallet, no `.env`, no network, no model downloads. The three external
boundaries (the face model, the search API and the blockchain) are substituted, while
everything between them runs as production code.

---

## What is covered

### `tests/test_record.py` (13 tests)

The tamper-evidence core. If any of these break, the project's central claim is false.

| Test | Asserts |
|---|---|
| `canonical_is_key_order_independent` | Two structurally equal records hash identically regardless of key order |
| `hash_is_stable_across_json_round_trip` | A record read back off disk hashes to the same value — floats, unicode and nesting all survive save → load |
| `hash_is_32_bytes` | The digest fits a Solidity `bytes32` exactly |
| `any_mutation_changes_the_hash` ×6 | Editing the URL, host, page title, face hash, detection score, or image hash each breaks the record hash |
| `verify_detects_tampering` | An altered record fails verification against its anchor |
| `verify_ignores_the_files_own_hash_field` | **The important one.** An attacker who edits the record *and* recomputes the `record_hash` beside it still fails, because verification compares against the chain, not the file |
| `embedding_never_enters_the_record` | The 512-d face vector is never written to the record — only its hash |
| `placeholder_env_values_are_treated_as_unset` | Copying `.env.example` to `.env` does not look like a configured key |

### `tests/test_reverse_search.py` (21 tests)

Social-platform detection and the no-fabrication guarantees.

| Test | Asserts |
|---|---|
| `social_urls_are_recognised` ×10 | X, Twitter (incl. `mobile.` subdomain), Instagram, Reddit, `youtu.be`, Pinterest (`.com` and `.co.uk`), Mastodon and Bluesky all resolve to the right platform |
| `non_social_urls_are_rejected` ×6 | News sites, Wikipedia, bare image hosts, empty strings, malformed URLs and non-HTTP schemes are all rejected |
| `lookalike_domain_is_not_treated_as_social` | `x.com.evil.net` does **not** match `x.com` — suffix matching is anchored on a label boundary, not a substring |
| `filter_social_dedupes_and_tags_host` | Duplicate URLs collapse; each result is tagged with its platform |
| `no_hardcoded_match_urls_in_source` | Scans the module source and fails if any social URL is baked in as a literal. The task forbids faked results, so this is enforced mechanically rather than by discipline |
| `provider_reports_unavailable_without_a_key` | With no credentials the pipeline returns zero matches — never a placeholder |
| `refuses_to_upload_without_a_public_url` | The privacy guard: the input photo is never auto-uploaded to a third-party host |

### `tests/test_pipeline_integration.py` (7 tests)

The whole pipeline through the real save-to-disk and load-from-disk path.

| Test | Asserts |
|---|---|
| `anchored_hash_is_reproducible_from_the_saved_file` | **The core contract.** The SHA-256 of the payload on disk equals the hash sent to the blockchain |
| `verify_reports_verified_for_an_untouched_record` | A clean record verifies |
| `verify_detects_a_file_tampered_on_disk` | A file edited on disk — sidecar hash updated too — reports `TAMPERED` |
| `chain_metadata_is_not_part_of_the_hashed_payload` | Transaction data is added *after* anchoring, so it must sit outside the hashed payload. If it leaked in, the hash could never be reproduced, since it is not known until after the write |
| `no_social_match_writes_nothing_on_chain` | No match means no chain write and no record file. The chain function is replaced with one that fails the test if called |
| `no_face_short_circuits_before_searching` | A photo with no face is never sent to a third-party search API |
| `mismatched_image_url_is_refused_before_anchoring` | A URL showing a different person aborts before touching the search API or the chain |

---

## Why the hash contract is tested twice

`test_record.py` checks hashing in memory. That would still pass if the saved file
structure and the hashed payload drifted apart, so `test_pipeline_integration.py`
independently checks that the hash handed to the blockchain is reproducible from the
file on disk.

The trap being guarded against: a stored record gains chain metadata (transaction hash,
block number) only *after* it has been hashed and anchored. If the file were hashed as a
whole, verification could never reproduce the anchored value. So the hashed payload sits
under a nested `record` key, and the `record_hash` field beside it is a convenience copy
that verification deliberately ignores.

```json
{
  "record":      { ... },   <-- hashed. never mutated after the write.
  "record_hash": "0x...",   <-- for humans. NOT trusted by verification.
  "chain":       { ... }    <-- added post-write. deliberately not hashed.
}
```

---

## Live verification evidence

The tests above are offline. These runs hit the real chain and the real search API.

### Contract deployment

```
[1/3] compiling FaceMatchRegistry.sol with solc 0.8.24 ...
      ok - 1920 bytes of bytecode
[2/3] connecting to Base Sepolia (https://sepolia.base.org) ...
      chain id 84532, block 46421734
      deployer 0xdcF01f543ADe441e2a7bD01541999b2cC28020d9  balance 0.0001 ETH
[3/3] deploying ...

====================================================================
  DEPLOYED to Base Sepolia
  address : 0x039E7A1234DD150522cb34a44Ca16056dC2B2daD
====================================================================
```

### Full end-to-end run

```
========================================================================
  FACE ID -> REVERSE IMAGE SEARCH -> BLOCKCHAIN
========================================================================
  [INPUT ] test_photo.jpg (282,530 bytes) sha256=0x6b478bb8bf188f22...
  [FACE  ] detecting and encoding face (InsightFace buffalo_l)...
  [FACE  ] face 1 found, det_score=0.831962, 512-d embedding, face_hash=0xca9759b74048d8e9...
  [VERIFY] confirming https://avatars.githubusercontent.com/u/1?v=4... is the same image
  [VERIFY] same image confirmed (face similarity 1.000)
  [SEARCH] querying Google Lens (SerpApi) against the live web index...
  [SEARCH] 6 total results, 2 on social platforms (providers: serpapi_google_lens)
  [MATCH ] youtube.com -> https://www.youtube.com/watch?v=hdVZKS_cnn0
  [HASH  ] record_hash=0x863cabb0b79b427642e0a0f9cc3d61f7249f113aaf22cd00e5f3639d189ffcf1
  [CHAIN ] anchoring on Base Sepolia...
  [CHAIN ] record #1 in block 46422170 (gas 188,344)
========================================================================
  RESULT: ANCHORED ON-CHAIN
========================================================================
```

Both links are live: the [matched post](https://www.youtube.com/watch?v=hdVZKS_cnn0) and
the [transaction](https://sepolia.basescan.org/tx/0xec9b9bfc6bcb35bcfed0485166b99a17a35fa76da05354c1699523f30ede2ac5).

### Verification, then tampering, then restoration

Clean record:

```
  on-chain hash   : 0x863cabb0b79b427642e0a0f9cc3d61f7249f113aaf22cd00e5f3639d189ffcf1
  recomputed hash : 0x863cabb0b79b427642e0a0f9cc3d61f7249f113aaf22cd00e5f3639d189ffcf1
  STATUS: VERIFIED
```

After editing one character of the match URL inside `records/1.json` — **and recomputing
the file's own `record_hash` so it looks internally consistent**:

```
  on-chain hash   : 0x863cabb0b79b427642e0a0f9cc3d61f7249f113aaf22cd00e5f3639d189ffcf1
  recomputed hash : 0x66318fd75e4e16a22365d6fb3227f3664c6f85ec1f3458bb5d0efefe4157ebd4
  STATUS: TAMPERED
  Local record does NOT match the on-chain hash. It was altered after being anchored.
```

Undoing the edit returns it to `VERIFIED`.

### Image-URL identity guard

The pipeline fetches the supplied public URL, encodes the face in it, and compares
embeddings before searching. Measured against the live model:

| Case | Cosine similarity | Outcome |
|---|---|---|
| Same image | **1.000** | Proceeds |
| A different person's photo | **0.069** | `image_url_mismatch` — aborts before the search API or the chain |

Without this, a mismatched URL would anchor one person's face hash against a search
performed on another person's photo, permanently.

### Verification with no credentials at all

Reading an anchored record with every key blanked, no wallet, no API key, no `.env`:

```
read WITHOUT any credentials:
   record_id         : 1
   face_hash         : 0xca9759b74048d8e9842771140ab2c90b02000cbc89b13713d5e77b3d16c9f1a4
   record_hash       : 0x863cabb0b79b427642e0a0f9cc3d61f7249f113aaf22cd00e5f3639d189ffcf1
   match_url         : https://www.youtube.com/watch?v=hdVZKS_cnn0
   submitter         : 0xdcF01f543ADe441e2a7bD01541999b2cC28020d9
   contract_address  : 0x039E7A1234DD150522cb34a44Ca16056dC2B2daD
```

And through `scripts/verify_standalone.py`, which imports nothing from this project:

```
========================================================================
  INDEPENDENT VERIFICATION (no keys, no wallet, public RPC only)
========================================================================
  chain           : Base Sepolia (84532), block 46422318
  contract        : 0x039E7A1234DD150522cb34a44Ca16056dC2B2daD
  records anchored: 2
------------------------------------------------------------------------
  hash ON-CHAIN   : 0x863cabb0b79b427642e0a0f9cc3d61f7249f113aaf22cd00e5f3639d189ffcf1
  hash RECOMPUTED : 0x863cabb0b79b427642e0a0f9cc3d61f7249f113aaf22cd00e5f3639d189ffcf1
========================================================================
  RESULT: VERIFIED
```

### Measured gas costs

At Base Sepolia's 0.006 gwei:

| Operation | Gas | Cost |
|---|---|---|
| Contract deployment | 467,003 | 0.0000056 ETH |
| One anchored record | ~188,000 | 0.0000024 ETH |

A single 0.1 ETH faucet drip covers thousands of runs.

---

## What is deliberately not tested

- **Face recognition accuracy.** InsightFace `buffalo_l` is a pretrained model used as-is;
  benchmarking ArcFace is not this project's job.
- **Google Lens result quality.** Whether Lens finds a match for a given photo depends on
  Google's index, not on this code. What *is* tested is that a no-match result produces
  no chain write and no fabricated URL.
- **Live network calls in the automated suite.** They would make the suite slow, flaky,
  and dependent on a paid quota. The live behaviour is captured above instead.
