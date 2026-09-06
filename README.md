# Face ID → Reverse Image Search → Blockchain

**Hacker House Goa 2026. Task #3**

A pipeline that detects and encodes a face from a photo, finds a **real** matching
social media post through **genuine** reverse-image search against a live web index,
and anchors that match on a public blockchain as a tamper-evident record.

No results are hardcoded, cached, or seeded anywhere in this repository. If the web
holds no match, the pipeline says so and writes nothing.

---

## What it does

```
input photo
    │
    ├─ sha256(image bytes)
    ▼
┌──────────────────────────────────────────────┐
│ 1. FACE          InsightFace buffalo_l       │  detect → largest face
│                  ArcFace 512-d, L2-normalised│  face_hash = sha256(embedding)
└──────────────────────────────────────────────┘
    ▼
┌──────────────────────────────────────────────┐
│ 2. SEARCH        Google Lens via SerpApi     │  live web index
│                  type=visual_matches         │  filter → social platforms only
└──────────────────────────────────────────────┘
    │
    ├─ no match ──► STOP. Nothing anchored. Nothing invented.
    ▼
┌──────────────────────────────────────────────┐
│ 3. RECORD        canonical JSON (sorted keys)│  record_hash = sha256(canonical)
└──────────────────────────────────────────────┘
    ▼
┌──────────────────────────────────────────────┐
│ 4. ANCHOR        Base Sepolia                │  FaceMatchRegistry.recordMatch()
│                  FaceMatchRegistry.sol       │  emits MatchRecorded
└──────────────────────────────────────────────┘
    ▼
records/{id}.json + tx hash + public explorer link
```

**Verification runs the other way:** read `recordHash` back off the chain, re-hash the
local record file, compare. Match → `VERIFIED`. Any difference → `TAMPERED`. Anyone
can do this against the public RPC without any credentials.

---

## Which blockchain

**Base Sepolia**, an Ethereum L2 testnet (OP-stack).

| | |
|---|---|
| Chain ID | `84532` |
| RPC | `https://sepolia.base.org` (public, no API key) |
| Explorer | https://sepolia.basescan.org |
| Contract | [`0x039E7A1234DD150522cb34a44Ca16056dC2B2daD`](https://sepolia.basescan.org/address/0x039E7A1234DD150522cb34a44Ca16056dC2B2daD) |
| Deploy tx | [`0xfd8d844e...c7ca4f6`](https://sepolia.basescan.org/tx/0xfd8d844ed40476fb3b662fe7ea117f05ebea5b3d64feeedb68fe392cbc7ca4f6) |
| Anchored records | 6 (`records/0.json` … `records/5.json`), each independently verifiable |

Chosen over Polygon Amoy because Polygon **deprecated its free public RPC endpoints in
July 2026**, which would have forced an extra third-party RPC key just to reach the
network. `CHAIN_RPC_URL` / `CHAIN_ID` are environment variables, so switching chains is
a config change, not a code change.

The contract is **append-only by design**, there is no update or delete function. An
anchor you can rewrite is not an anchor.

---

## How to run it

### 1. Install

```bash
cd backend
py -3.11 -m venv faceid
faceid\Scripts\activate          # Windows
# source faceid/bin/activate     # macOS / Linux
pip install -r requirements.txt
```

Python **3.11.9**. On first run, InsightFace downloads the `buffalo_l` model pack
(~300 MB) into `~/.insightface/models/`.

### 2. Configure

```bash
cp .env.example .env
```

Fill in:

| Variable | Where to get it |
|---|---|
| `SERPAPI_KEY` | [serpapi.com](https://serpapi.com) — free, 250 searches/month, **no card** |
| `WALLET_PRIVATE_KEY` | A **throwaway** wallet, funded free from the [Coinbase CDP faucet](https://portal.cdp.coinbase.com/products/faucet) (no mainnet balance needed) |

Generate a throwaway wallet, the private key never leaves your machine:

```bash
python -c "from eth_account import Account; a=Account.create(); print('ADDRESS:', a.address); print('PRIVATE KEY:', a.key.hex())"
```

Put the private key in `.env`; paste the address into the faucet to receive 0.1 test ETH.
Testnet ETH is fake money with no market value, it only pays network fees.

**The entire project runs on free tiers with no payment method anywhere in the stack.**

`.env` is gitignored. Never point this at a wallet holding real funds.

### 3. Deploy the contract *(optional)*

A deployed contract already ships in `contracts/FaceMatchRegistry.json`, so the pipeline
works immediately. To deploy your own:

```bash
python scripts/deploy_contract.py
```

It prints the deployed address, paste it into `.env` as `CONTRACT_ADDRESS`. The ABI and
address are written to `contracts/FaceMatchRegistry.json`, which is committed, so
reproducing a run never requires a Solidity compiler.

### 4. Check everything is wired up

```bash
python scripts/run_pipeline.py --health
```

### 5. Run the pipeline

```bash
python scripts/run_pipeline.py photo.jpg --image-url https://already-public-url/photo.jpg
```

`--image-url` is **required**: Google Lens can only search a publicly reachable URL, and
this pipeline never uploads your photo anywhere (see *Privacy*). It must point at the
same image, the pipeline fetches it and compares face embeddings before searching.

**Choosing a photo matters.** Reverse-image search matches *images*, not faces, so the
photo has to already exist online. A photo of yourself posted on X, LinkedIn or Reddit
works well; so does a GitHub avatar
(`https://avatars.githubusercontent.com/u/<your-id>?v=4`). A brand-new selfie will
correctly return `no_social_match`.

### 6. Verify the anchored record

```bash
python scripts/run_pipeline.py --verify 0
```

To **see tamper-evidence work**, edit one character of the URL inside `records/0.json`,
then run `--verify 0` again. It flips to `TAMPERED`.

### Optional HTTP API

Hosting is not required by the task; the CLI above is the canonical demo. The same
pipeline is exposed over HTTP if you want to inspect stages interactively:

```bash
uvicorn app.main:app --reload
```

`GET /api/health` · `POST /api/verify` · `GET /api/record/{id}` · docs at `/api/docs`

### If a run does not do what you expect

| Message | Meaning |
|---|---|
| `--image-url is required` | Lens cannot search local bytes, and your photo is never uploaded. Pass the URL where the same image is already published. |
| `IMAGE URL MISMATCH` | The URL shows a different face than your file. A safety guard — supply the correct URL. |
| `NO SOCIAL MATCH` | Working as intended. Lens found no social page hosting this image, so nothing was written on-chain. |
| `NO FACE` | No detectable face, or a corrupt file. Some hosts (Wikimedia) block automated downloads and return HTML instead of an image. |
| `wallet ... has zero balance` | Top up from the faucet, then re-run `--health`. |

Exit codes: `0` success · `1` usage/config · `2` no face · `3` no social match ·
`4` tampered · `5` image-URL mismatch.

### Tests

```bash
pytest -q      # 41 passed
```

41 offline tests covering the hashing contract, tamper detection, the social-domain
filter and the no-fabrication guarantees. No network, models or chain required. The full
inventory and the live verification evidence are in [`TESTING.md`](TESTING.md).

---

## Known limitations

These are properties of the problem, stated plainly rather than hidden.

1. **Reverse-image search matches images, not face identity.** Google Lens does not
   perform face-identity search. Google deliberately does not offer it. This pipeline
   finds pages hosting *this same photograph*. **Consequently the
   input photo must already exist online for a match to be found.** The face encoding
   is a biometric fingerprint that binds the record to its input; it is not the search
   key. Feeding in a brand-new selfie will correctly return `no_social_match`.

2. **Social platform indexing is uneven.** Instagram and Facebook are poorly indexed by
   Google at the individual-post level. X/Twitter, Reddit, Pinterest and YouTube match
   far more reliably.

3. **Google Lens needs an already-public image URL.** It cannot accept local bytes, and
   the input photo is deliberately **not** auto-uploaded to an image host to work around
   that, see *Privacy* below.

   The SerpApi Lens engine also **requires an explicit `type` parameter**. Google
   changed the Lens layout, and without it the response contains only an `ai_overview`
   and no match lists at all. We pass `type=visual_matches`.

4. **Google Cloud Vision was evaluated and rejected.** Its `WEB_DETECTION` feature does
   the same job and accepts local bytes, which would remove the public-URL requirement.
   But Vision demands a Cloud billing account with a payment method even for its free
   1,000 units/month, and in some regions (India among them) a **one-time ₹1,000
   prepayment** on top. That is a poor trade for a project that is otherwise entirely
   free to run, so the integration was removed rather than left as dead code. Adding it
   back is a single module implementing the same `search_*` shape.

5. **Testnet, not mainnet.** Base Sepolia records are immutable and publicly
   verifiable, but the chain is not economically secured the way mainnet is. Moving to
   Base mainnet is a two-variable config change.

6. **One face per photo.** The largest detected face is used; `face_count` is reported
   honestly in the record so a crowded photo is visible as such.

7. **InsightFace `buffalo_l` is licensed for non-commercial research use.** Fine for a
   hackathon; would need replacing for a commercial deployment.

8. **SerpApi free tier is capped** at 250 searches/month.

9. **A match is a claim, not a verdict.** The registry proves a specific claim existed
   unmodified at a specific block. It does not assert the match is correct. The
   contract is permissionless precisely because it makes no truth claim.

---

## Privacy and responsible use

This pipeline can link a face to a social media identity, so a few decisions were made
deliberately rather than by default:

- **No biometric data is ever published.** Only `sha256(embedding)` is written on-chain.
  The 512-d vector never leaves the local process and cannot be recovered from the hash.
  A recoverable face embedding on a permanent public ledger is irreversible.
- **The input photo is never auto-uploaded anywhere.** Google Lens can only search a
  public URL, so the operator supplies one for an image that is *already* public. The
  documented workaround of uploading to an image host first was deliberately rejected.
- **A mismatched `--image-url` is refused.** Before searching, the pipeline fetches the
  supplied URL, encodes the face in it, and compares embeddings. Below 0.9 cosine
  similarity it aborts without touching the chain. Otherwise a careless or malicious
  URL would anchor *this* face against a search for *someone else's* photo, a false
  record that could never be deleted. Verified: 1.000 for the same image, 0.069 for a
  different person.
- **Anchoring is permanent.** The match URL and face hash cannot be deleted afterwards.
  Consider that before running this on anyone.
- **Use it on your own photo, or on a public figure whose images are already widely
  published.** Do not use it to deanonymise a private individual.

---

## Layout

```
backend/
├── app/
│   ├── config.py               environment loading, placeholder detection
│   ├── face.py                 InsightFace detection + ArcFace encoding
│   ├── reverse_search.py       Google Lens (SerpApi) + social-domain filter
│   ├── record.py               canonical JSON, hashing, storage
│   ├── chain.py                web3 write / read-back
│   ├── pipeline.py             orchestration shared by the CLI and the API
│   └── main.py                 FastAPI app
├── contracts/
│   ├── FaceMatchRegistry.sol   the registry contract
│   └── FaceMatchRegistry.json  committed ABI + deployed address
├── scripts/
│   ├── deploy_contract.py      compile and deploy, run once
│   ├── run_pipeline.py         the main CLI
│   └── verify_standalone.py    independent check, no keys or project imports
├── tests/
│   ├── test_record.py          hashing and tamper detection
│   ├── test_reverse_search.py  domain filtering, no-fabrication guarantees
│   └── test_pipeline_integration.py   full pipeline through the disk round-trip
├── records/                    one JSON file per anchored run (0-5 committed)
├── inputs/                     local input photos (gitignored)
├── faceid/                     virtualenv, Python 3.11.9 (gitignored)
├── README.md                   this file
├── USER_GUIDE.md               setup, verification and troubleshooting
├── TESTING.md                  test suite and captured verification output
├── ARCHITECTURE.md             design rationale, decisions and research
├── requirements.txt            pinned dependencies
├── conftest.py                 lets bare `pytest` find the app package
├── .env.example                configuration template, placeholders only
├── .gitignore
└── LICENSE                     MIT
```

`.env` and `inputs/` are gitignored, so credentials and input photos never leave
your machine.

Design rationale, the research behind each dependency choice, and the rejected
alternatives are documented in [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Stack

Python 3.11.9 · FastAPI · InsightFace (ONNX Runtime, CPU) · OpenCV · web3.py 8 ·
Solidity 0.8.24 · SerpApi Google Lens · Base Sepolia
