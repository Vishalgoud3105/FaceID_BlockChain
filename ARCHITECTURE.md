# Architecture and Design Notes

Face ID → Reverse Image Search → Blockchain
Hacker House Goa 2026, Task #3

This document covers why the project is built the way it is: what was chosen, what was
rejected, and what had to change once the code hit real APIs. Setup and usage
instructions are in `USER_GUIDE.md`.

---

## 1. Requirements

The task asks for four things:

1. Detect and encode a face from an input image, using any library or API
2. Find at least one real matching social media post through genuine reverse-image
   search, with no hardcoded results
3. Write the match to a blockchain as a tamper-evident, verifiable record
4. No website or hosting is needed; the pipeline itself is what gets judged

Deliverables are a GitHub repo with a README covering functionality, how to run it, which
blockchain was used and known limitations, plus an unedited screen recording of one run.

Three things follow from that brief and drove most of the decisions below: the match has
to be genuine, the record has to be tamper-evident, and the run has to be reproducible.
Nothing here is optimised for looking good in a UI.

---

## 2. Pipeline

```
  input photo (bytes)  +  public URL of that same photo
        │
        ├─► sha256(image bytes) ──────────────────► image_sha256
        ▼
  ┌───────────────────────────────┐
  │ app/face.py                   │   InsightFace buffalo_l (ONNX, CPU)
  │  detect → largest face        │   det_size 640x640
  │  512-d ArcFace embedding      │   L2-normalised
  │  face_hash = sha256(emb)      │   only the hash is ever published
  └───────────────────────────────┘
        │   (blocking, so run_in_executor)
        ▼
  ┌───────────────────────────────┐
  │ app/pipeline.py               │   fetch the URL, encode its face,
  │  image-URL identity guard     │   cosine-compare with the local one
  └───────────────────────────────┘
        │
        ├── similarity < 0.9 ──► stop. `image_url_mismatch`.
        ▼
  ┌───────────────────────────────┐
  │ app/reverse_search.py         │   Google Lens through SerpApi
  │  reverse-image search         │   type=visual_matches (required)
  │  filter to social domains     │
  └───────────────────────────────┘
        │
        ├── no social match ──► stop. `no_social_match`. Nothing anchored.
        ▼
  ┌───────────────────────────────┐
  │ app/record.py                 │   canonical JSON, sorted keys, no whitespace
  │  record_hash = sha256(canon)  │
  └───────────────────────────────┘
        ▼
  ┌───────────────────────────────┐
  │ app/chain.py                  │   Base Sepolia, chain id 84532
  │  recordMatch(faceHash,        │   FaceMatchRegistry.sol
  │              recordHash, url) │   emits MatchRecorded
  └───────────────────────────────┘
        ▼
  records/{id}.json   +   tx hash   +   explorer link
```

Verification runs in the opposite direction. Read `recordHash` off the chain, re-hash the
local record file, compare the two. Equal means `VERIFIED`, different means `TAMPERED`.
That path needs no API keys, no wallet and no `.env`, only the public RPC, so anyone can
check a record independently.

---

## 3. Decisions

Each of these was checked against the live API or the installed package before being
committed to, since several of the obvious defaults turned out to be stale.

| Area | Chosen | Reasoning |
|---|---|---|
| Reverse image search | Google Lens through SerpApi | 250 free searches a month with no payment method. Returns real pages hosting the image from Google's live index. Needs `type=visual_matches`, see §7.3. |
| Rejected | Google Cloud Vision `WEB_DETECTION` | Technically the better fit, since it accepts raw bytes and would remove the public-URL requirement. It requires a Cloud billing account with a payment method even for the free 1,000 units a month, and in India a ₹1,000 prepayment on top. Removed rather than shipped as an unusable path. See §7.5. |
| Blockchain | Base Sepolia, chain id 84532 | Public RPC at `https://sepolia.base.org` needs no key, faucets are free, blocks are fast, and the explorer is public. The only secret required is a funded throwaway private key. |
| Rejected | Polygon Amoy | Polygon deprecated its free public RPC endpoints in July 2026. Amoy would have needed a third-party RPC key just to reach the network. |
| On-chain form | Contract with an event | `recordMatch()` writes to an array and emits `MatchRecorded`, which gives both an on-chain read-back and a decoded event in the explorer. Putting the hash in raw calldata would be equally tamper-evident but offers no way to read it back. |
| Contract design | Append-only, permissionless | No update or delete function exists. Permissionless because the registry records that a claim was made, not that it is true. |
| Face model | InsightFace `buffalo_l`, version 1.0.1 or later | Reuses a pattern already working in an earlier face-recognition project. Version 1.0 stopped building the `face3d` Cython extension by default, which removes the old "Failed building wheel for insightface" problem on Windows. No C++ toolchain needed. |
| Python | 3.11.9, venv at `backend/faceid` | Best wheel availability for the ONNX and OpenCV stack. |
| torch removed | — | It was only needed for the anti-spoof model, which was cut (§4). InsightFace runs on `onnxruntime`, so dropping torch saves roughly 2 GB. |
| web3.py | v8, pinned at `8.0.0` | The original plan targeted v7; pip resolved v8. Checked against the installed package, see §7.1. |
| Solidity compile | `py-solc-x`, run once | The ABI and address are committed in `contracts/FaceMatchRegistry.json`, so reproducing a run never needs solc. Needs a download-host override, see §7.2. |

---

## 4. What was deliberately left out

No anti-spoof or liveness model. The earlier face-recognition project used
`EfficientNetB0_AntiSpoof.pt`, which classifies still photographs as spoofs by design.
Including it would make this pipeline reject its own input. The task asks for detection
and encoding, not liveness.

No video ingestion. The frame extraction and multi-frame voting in the earlier project
exist to support liveness checking. With a single still photo there is nothing to vote
across.

Multiple faces are not rejected. The earlier project errors out when it sees more than
one face, because it is an attendance system where ambiguity causes wrong records. Here
the input is an arbitrary photo that may well contain bystanders, so the largest bounding
box is selected and `face_count` is recorded so a crowded photo is visible in the output.

No database, no authentication, no frontend. None of it is required or judged.

No raw biometric data on-chain. Only `sha256(embedding)` is published.

---

## 5. Privacy

The pipeline links a face to a social identity and writes the result somewhere it cannot
be deleted. Four decisions follow from that.

Only a hash of the embedding is published. The 512-d vector stays in the local process
and cannot be recovered from the hash. Putting a usable face embedding on a permanent
public ledger would be impossible to undo later.

The input photo is never uploaded automatically. Google Lens can only search a public
URL, and the usual workaround is to upload the image to S3 or an image host first. That
was rejected. Publishing someone's face to a third party without asking them is not a
reasonable default, so the operator supplies a URL for an image that is already public.

A mismatched URL is refused before anything is anchored. See §7.6.

Responsible-use guidance is in the code as well as the docs. The CLI docstring and the
README both say to run this on your own photo or on a public figure, and not to use it to
identify a private individual.

---

## 6. Limitations

These are properties of the problem rather than defects, and they are stated in the
README as well.

1. Lens matches images, not face identity. Google does not offer face-identity search.
   The pipeline finds pages hosting the same photograph, which means the input photo has
   to already exist online. The face encoding ties the record to its input; it is not the
   search key.
2. Social platforms are indexed unevenly. Instagram and Facebook are poor at the
   individual-post level. X, Reddit, Pinterest and YouTube work much better.
3. A public image URL is required, because Lens cannot search local bytes.
4. This is a testnet. Records are immutable and publicly verifiable, but Base Sepolia is
   not economically secured the way mainnet is. Moving to mainnet is two env vars.
5. InsightFace `buffalo_l` is licensed for non-commercial research use.
6. SerpApi's free tier allows 250 searches a month.
7. A run with no match writes nothing. This is intentional. Returning `no_social_match`
   is the correct outcome when the search genuinely finds nothing, and inventing a URL to
   keep a demo moving is what the no-hardcoded-results rule exists to prevent.
8. A match is a claim, not a verdict. The registry shows that a specific claim existed
   unmodified at a specific block. It says nothing about whether the match is correct.

---

## 7. Things that changed during the build

Seven assumptions turned out to be wrong once the code met the actual environment. They
are recorded here because each one is a trap somebody else would otherwise hit.

### 7.1 web3.py resolved to v8, not v7

The plan targeted v7 and pip installed v8. Checking the installed package rather than the
changelog: the signed-transaction attribute is still `raw_transaction` in snake_case,
`ExtraDataToPOAMiddleware` still exists, and `build_transaction` and `process_receipt`
are unchanged. No code changes were needed. The version is pinned at `web3==8.0.0`
because that is what was actually tested.

### 7.2 py-solc-x downloads from a host that no longer exists

`py-solc-x` 2.0.3 has `solc-bin.ethereum.org` hardcoded, and that hostname no longer
resolves. DNS fails for it while every other host in the stack resolves fine, which is
how it was diagnosed. Solidity moved its binaries to `binaries.soliditylang.org`, so
`scripts/deploy_contract.py` overrides `BINARY_DOWNLOAD_BASE` before any download
happens. The compiled artifact is committed, so a normal reproduction never calls solc
at all.

### 7.3 SerpApi Lens returns nothing without a `type` parameter

This was the worst of the seven, because it fails silently. A Lens request without an
explicit `type` comes back as HTTP 200 carrying only an `ai_overview`, with no
`visual_matches`, no `exact_matches` and no error field. The result is indistinguishable
from a genuine "no match found". Google changed the Lens layout at some point and
`type=visual_matches` is now required. It was only diagnosed by dumping the raw response
keys and noticing what was absent.

### 7.4 SerpApi has no endpoint for uploading local images

The original design assumed an upload endpoint that returns an `image_id`. There isn't
one. Lens accepts a publicly reachable URL and nothing else. The documented workaround is
to upload the image to your own S3 bucket first, which was rejected for the privacy
reason in §5.

### 7.5 Google Vision was removed completely

Vision started as the primary provider. The API key authenticated correctly but every
call came back with `403 This API method requires billing to be enabled`. Enabling
billing needs a payment method even for the free tier, and in India there is a one-time
₹1,000 prepayment before billing activates. For a project that is otherwise free from end
to end, that is a bad trade.

It was kept briefly as a graceful-degradation path and then deleted. Keeping a provider
that can never succeed means shipping an unexercised code path, a 403 handler, a config
key, tests and documentation for something nobody can run.
`find_social_match(image_bytes, image_url)` became `find_social_match(image_url)`, since
the bytes only ever existed for Vision, and `--image-url` went from conditionally
required to always required, which is the clearer state anyway. Adding Vision back would
mean writing one module with the same `search_*` shape; nothing else depends on it.

### 7.6 Nothing checked that `--image-url` showed the same image

Making `--image-url` mandatory exposed a gap the earlier design never addressed. If the
URL points at a different photo, the pipeline would anchor the local photo's `face_hash`
against a search performed on someone else's image. That produces a false record which
can never be removed, and it is exactly the kind of fabricated match the task prohibits.

`app/pipeline.py` now fetches the URL, encodes the face in it, and compares the two
embeddings by cosine similarity before running any search. Below `URL_MATCH_THRESHOLD`,
currently 0.9, the run stops with `image_url_mismatch` without calling the search API or
the chain. If the URL cannot be fetched at all, the run continues but records
`image_url_check.verified = null`, so the output never implies a check that did not
happen.

Measured against the live model, the same image scores 1.000 and a different person
scores 0.069.

### 7.7 `app/pipeline.py` was added

Orchestration was originally going to live in `app/main.py`, with the CLI calling the
same service functions. That would have forced the CLI to import FastAPI just to reuse
them. It lives in `app/pipeline.py` instead, called by both `main.py` and
`scripts/run_pipeline.py`, so there is only one copy of the pipeline sequence and the CLI
being screen-recorded runs exactly what the API runs.

---

## 8. What was verified by running it

- Dependencies install and import on Python 3.11.9, with `insightface` 1.0.1 alongside
  `numpy` 2.1.3 and no compiler required
- `FaceMatchRegistry.sol` compiles under solc 0.8.24, producing 1,920 bytes of bytecode
- Live connection to Base Sepolia, chain id 84532, at block 46,422,318
- Face detection and encoding on a real photo containing six faces: the largest was
  selected, det_score 0.92, 512-d embedding with an L2 norm of exactly 1.0, and the hash
  was identical across repeated runs
- A live Google Lens search returning 6 results, 2 of them on social platforms
- A full end-to-end run anchoring record #1 in block 46422170 using 188,344 gas
- Verification, where the on-chain hash matched the recomputed one
- Tamper detection, where an edit to the record file was caught even after the sidecar
  `record_hash` was recomputed to match, because verification compares against the chain
- The image-URL guard, scoring 1.000 on the same image and 0.069 on a different person,
  refusing the second before reaching the search API or the chain
- Verification with no credentials at all, both by reading the record with every key
  blanked and through `scripts/verify_standalone.py`, which imports nothing from this
  project
- 41 offline tests, including both passes over the hashing contract described in §11

Details and captured output for all of the above are in `TESTING.md`.

---

## 9. Deployment

| | |
|---|---|
| Contract | `0x039E7A1234DD150522cb34a44Ca16056dC2B2daD` |
| Chain | Base Sepolia, 84532 |
| Deploy tx | `0xfd8d844ed40476fb3b662fe7ea117f05ebea5b3d64feeedb68fe392cbc7ca4f6` |
| Record #1 | `0xec9b9bfc6bcb35bcfed0485166b99a17a35fa76da05354c1699523f30ede2ac5` |
| Cost | roughly 0.0000056 ETH to deploy and 0.0000024 ETH per record, at 0.006 gwei |

---

## 10. Layout

```
backend/
├── faceid/                     venv (py 3.11.9), gitignored
├── README.md                   project overview and usage
├── USER_GUIDE.md               setup, verification and troubleshooting
├── TESTING.md                  test suite and captured verification output
├── requirements.txt
├── .env.example                placeholders only
├── conftest.py                 lets bare `pytest` find the app package
├── ARCHITECTURE.md             this file
├── contracts/
│   ├── FaceMatchRegistry.sol
│   └── FaceMatchRegistry.json  committed ABI and deployed address
├── scripts/
│   ├── deploy_contract.py      run once
│   ├── run_pipeline.py         the CLI used for the demo
│   └── verify_standalone.py    independent check, no keys or project imports
├── app/
│   ├── config.py               env loading, placeholder detection
│   ├── face.py                 detection and encoding
│   ├── reverse_search.py       Google Lens and the social-domain filter
│   ├── record.py               canonical JSON and hashing
│   ├── chain.py                web3 write and read-back
│   ├── pipeline.py             orchestration shared by the CLI and the API
│   └── main.py                 FastAPI
├── tests/                      41 offline tests
└── records/                    one JSON file per anchored run
```

---

## 11. Notes on how this was tested

Check things against the live API or the installed package rather than the
documentation. Seven assumptions in the original design were wrong (§7), and all of them
surfaced by running code rather than reading about it. §7.3 is the reason this matters: a
missing query parameter came back as HTTP 200 with an empty result set, which looks the
same as a real no-match. An integration that fails loudly wastes an hour. One that
quietly returns nothing can make it all the way into a demo.

The hashing contract is tested twice, in two different ways. It is easy to get wrong
without noticing, because a normal successful run still passes when it is broken, and it
matters more than anything else here since tamper-evidence is the whole point. The first
set of tests covers hashing in memory. The second covers reproducibility through the real
save-to-disk and load-from-disk path, which is where this kind of thing usually breaks: a
stored record picks up chain metadata after it has been hashed, so the hashed payload has
to sit under its own key, and verification has to compare the chain's hash against one
recomputed from the file rather than the copy stored alongside it.

Failure paths get the same attention as successful ones. A pipeline that invents a match
when the search finds nothing would sail through a casual demo while failing the actual
requirement. There are explicit tests asserting that no chain write happens without a
real match, that no search runs when no face was found, and that a mismatched image URL
stops the run before either the search API or the chain is touched.
