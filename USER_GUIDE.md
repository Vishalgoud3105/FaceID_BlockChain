# User Guide. Running & Verifying This Project

**Hacker House Goa 2026 · Task #3. Face ID + Blockchain Verification**

Everything here has been executed and the outputs below are copied verbatim from real
runs. Nothing is illustrative.

**Cost to run: ₹0.** Free search tier, free testnet, free public RPC, free faucet. No
payment method is required anywhere in this stack.

---

## What this project does

It takes a photograph, detects and encodes the face in it, finds a real social media post
containing that same image through a live reverse-image search, and writes a hash of the
result to a public blockchain so the record cannot be altered afterwards without it being
obvious.

```
photo ──► face detected + encoded ──► reverse-image search ──► social post found
                                                                      │
                                    record hashed (SHA-256) ◄──────────┘
                                                │
                                                ▼
                                   anchored on Base Sepolia
```

Four things are worth knowing before you run it:

- **The search matches images, not faces.** Google Lens does not do face-identity search.
  This finds pages hosting *that same photograph*, so the input photo must already exist
  online. A brand-new selfie will correctly find nothing.
- **No biometric data is published.** Only `sha256(embedding)` goes on-chain. The 512-d
  face vector never leaves the local machine and cannot be recovered from the hash.
- **Nothing is ever fabricated.** If the search finds no social post, the pipeline says so
  and writes nothing to the chain.
- **Verification needs no credentials.** Anyone can check an anchored record against the
  public chain without keys, a wallet, or a `.env` file, that is §1 and §2 below.

---

## Contents

| Section | For whom | Time |
|---|---|---|
| [1. Verify without installing anything](#1-verify-without-installing-anything) | Judges | 1 min |
| [2. Verify by running our code](#2-verify-by-running-our-code) | Judges | 5 min |
| [3. Full setup — run the whole pipeline](#3-full-setup--run-the-whole-pipeline) | Anyone | 15 min |
| [4. The tamper-evidence demo](#4-the-tamper-evidence-demo) | Everyone | 2 min |
| [5. Optional HTTP API](#5-optional-http-api) | Anyone | 2 min |
| [6. Troubleshooting](#6-troubleshooting) | Anyone | — |
| [7. Exit codes](#7-exit-codes) | Anyone | — |
| [8. Known limitations](#8-known-limitations) | Anyone | 2 min |

**Live deployment referenced throughout:**

| | |
|---|---|
| Chain | Base Sepolia (chain id `84532`) |
| Contract | [`0x039E7A1234DD150522cb34a44Ca16056dC2B2daD`](https://sepolia.basescan.org/address/0x039E7A1234DD150522cb34a44Ca16056dC2B2daD) |
| Example record | `#1` — `records/1.json` |

---

## 1. Verify without installing anything

**The strongest check requires none of this project's code at all.** Open the contract on the public
block explorer:

> https://sepolia.basescan.org/address/0x039E7A1234DD150522cb34a44Ca16056dC2B2daD

Under **Events** you will see `MatchRecorded` entries. Each carries the record id, the
face hash, the record hash, and the matched social media URL, written permanently to a
public chain. Under **Contract → Read Contract**, call `getRecord(1)` to read record #1
directly. Call `total()` to see how many records exist.

Nothing on that page comes from this project. It is the chain's own view.

---

## 2. Verify by running this project's code

This proves the anchored record has not been altered. **It needs no API keys, no wallet,
and no `.env` file**, only the public RPC.

```bash
git clone <repo-url>
cd backend
py -3.11 -m venv faceid
faceid\Scripts\activate           # Windows
# source faceid/bin/activate      # macOS / Linux
pip install web3
```

Then run the standalone verifier, which **imports nothing from this project**, it is
~120 self-contained lines you can read top to bottom:

```bash
python scripts/verify_standalone.py 1 records/1.json
```

**Actual output:**

```
========================================================================
  INDEPENDENT VERIFICATION (no keys, no wallet, public RPC only)
========================================================================
  chain           : Base Sepolia (84532), block 46422318
  contract        : 0x039E7A1234DD150522cb34a44Ca16056dC2B2daD
  records anchored: 2
------------------------------------------------------------------------
  record id       : 1
  anchored url    : https://www.youtube.com/watch?v=hdVZKS_cnn0
  face hash       : 0xca9759b74048d8e9842771140ab2c90b02000cbc89b13713d5e77b3d16c9f1a4
  anchored at     : block timestamp 1788612628
  submitted by    : 0xdcF01f543ADe441e2a7bD01541999b2cC28020d9
------------------------------------------------------------------------
  hash ON-CHAIN   : 0x863cabb0b79b427642e0a0f9cc3d61f7249f113aaf22cd00e5f3639d189ffcf1
  hash RECOMPUTED : 0x863cabb0b79b427642e0a0f9cc3d61f7249f113aaf22cd00e5f3639d189ffcf1
========================================================================
  RESULT: VERIFIED
```

> The `records anchored` count reflects the chain at the time this output was
> captured. It increases with every run, so a live check today will show more.

**What just happened:** the script read `recordHash` off the blockchain, independently
recomputed the SHA-256 of `records/1.json`, and compared them. Equal means the file is
byte-for-byte what was anchored.

To see it fail, change any character inside the `"record"` object of `records/1.json`
and run it again, see [section 4](#4-the-tamper-evidence-demo).

---

## 3. Full setup, run the whole pipeline

### 3.1 Prerequisites

- **Python 3.11** (3.11.9 tested). Check: `py -3.11 --version`
- ~500 MB free disk. InsightFace downloads a ~300 MB model pack on first run
- Internet access

### 3.2 Install

```bash
cd backend
py -3.11 -m venv faceid
faceid\Scripts\activate           # Windows
# source faceid/bin/activate      # macOS / Linux
pip install -r requirements.txt
```

No C++ compiler is needed. InsightFace ≥1.0 no longer builds its Cython extension by
default, which was the historic Windows install failure.

### 3.3 Get the two free credentials

**A. SerpApi key** (reverse-image search; free 250 searches/month, **no card**)

1. Sign up at https://serpapi.com/users/sign_up
2. Copy your key from https://serpapi.com/manage-api-key

**B. A throwaway wallet, funded with free testnet ETH**

Generate a keypair. The private key never leaves your machine:

```bash
python -c "from eth_account import Account; a=Account.create(); print('ADDRESS:', a.address); print('PRIVATE KEY:', a.key.hex())"
```

Fund the **address** at https://portal.cdp.coinbase.com/products/faucet, sign in,
select network **Base Sepolia**, token **ETH**, paste the address. You get 0.1 ETH.

> This is **testnet** ETH: fake money with no market value, used only to pay network
> fees while testing. Never put a wallet holding real funds in `.env`.
>
> The Coinbase faucet is recommended because it has **no mainnet-balance requirement**.
> The Alchemy and QuickNode faucets require you to already hold ~0.001 real ETH.

**Cost reference (measured on-chain):** at Base Sepolia's 0.006 gwei, deploying the
contract costs ~0.0000056 ETH and each anchored record ~0.0000024 ETH. A single 0.1 ETH
drip covers thousands of runs.

### 3.4 Configure

```bash
cp .env.example .env
```

Edit `.env`:

```
SERPAPI_KEY=<your serpapi key>
WALLET_PRIVATE_KEY=<your private key>
```

Leave everything else at its default. `.env` is gitignored.

> Placeholder values from `.env.example` are detected and treated as unset, so a
> half-filled file reports honestly rather than failing later at the API call.

### 3.5 Deploy your own contract *(optional)*

**Skip this to use the already-deployed contract**, its address ships in
`contracts/FaceMatchRegistry.json`, so the pipeline works immediately.

To deploy your own:

```bash
python scripts/deploy_contract.py
```

Then put the printed address into `.env` as `CONTRACT_ADDRESS`.

### 3.6 Check everything is wired up

```bash
python scripts/run_pipeline.py --health
```

**Actual output:**

```json
{
  "missing_config": [],
  "search_provider": {
    "serpapi_google_lens": true
  },
  "chain": {
    "chain_name": "Base Sepolia",
    "rpc_url": "https://sepolia.base.org",
    "chain_id_expected": 84532,
    "connected": true,
    "chain_id_actual": 84532,
    "block_number": 46422163,
    "wallet": "0xdcF01f543ADe441e2a7bD01541999b2cC28020d9",
    "balance_eth": 9.5903090077483e-05,
    "funded": true
  }
}
```

You want `missing_config: []`, `connected: true`, and `funded: true`.

### 3.7 Choose an input photo, read this before running

Reverse-image search matches **images, not faces**. Google Lens does not do
face-identity search. This pipeline finds pages hosting *this same photograph*.

**Therefore your photo must already exist online, and you must supply its public URL.**
A brand-new selfie will correctly return `no_social_match`.

Good choices:

- A photo of yourself already posted on X / LinkedIn / Reddit
- Your GitHub avatar: `https://avatars.githubusercontent.com/u/<your-id>?v=4`
- Any public figure whose images are widely published

> **Responsible use.** This links a face to a social identity and writes the result to a
> permanent public ledger that cannot be deleted. Run it on your own photo or on a
> public figure. Do not use it to deanonymise a private individual.

### 3.8 Run the pipeline

```bash
python scripts/run_pipeline.py inputs/test_photo.jpg \
    --image-url "https://avatars.githubusercontent.com/u/1?v=4"
```

`--image-url` is **required**. Google Lens can only search a publicly reachable URL, and
this pipeline deliberately never uploads your photo anywhere. It must point at the same
image, the pipeline fetches it and compares face embeddings before searching.

**Actual output:**

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
  [CHAIN ] https://sepolia.basescan.org/tx/0xec9b9bfc6bcb35bcfed0485166b99a17a35fa76da05354c1699523f30ede2ac5
  [SAVED ] ...\records\1.json
========================================================================
  RESULT: ANCHORED ON-CHAIN
  match       : https://www.youtube.com/watch?v=hdVZKS_cnn0
  platform    : youtube.com
  face hash   : 0xca9759b74048d8e9842771140ab2c90b02000cbc89b13713d5e77b3d16c9f1a4
  record hash : 0x863cabb0b79b427642e0a0f9cc3d61f7249f113aaf22cd00e5f3639d189ffcf1
  chain       : Base Sepolia (id 84532)
  contract    : 0x039E7A1234DD150522cb34a44Ca16056dC2B2daD
  record id   : 1
  tx          : 0xec9b9bfc6bcb35bcfed0485166b99a17a35fa76da05354c1699523f30ede2ac5
  explorer    : https://sepolia.basescan.org/tx/0xec9b9bfc...
  saved       : ...\records\1.json
========================================================================
  Verify it:  python scripts/run_pipeline.py --verify 1
========================================================================
```

**Reading the stages:**

| Stage | What it proves |
|---|---|
| `INPUT` | SHA-256 of the exact bytes supplied |
| `FACE` | A real face was detected and encoded into a 512-d ArcFace vector. Only its **hash** is ever published — the vector never leaves your machine |
| `VERIFY` | The public URL shows the same face (cosine similarity ≥ 0.9), so the search and the encoding refer to the same image |
| `SEARCH` | A live Google Lens query. No cached or seeded results exist anywhere in this repo |
| `MATCH` | A genuine social media URL you can open in a browser |
| `HASH` | The canonical record hashed to 32 bytes |
| `CHAIN` | A real transaction, publicly inspectable |

**Open the match URL and the explorer link.** Both are real.

### 3.9 Verify what you just anchored

```bash
python scripts/run_pipeline.py --verify 1
```

**Actual output:**

```
========================================================================
  VERIFYING RECORD #1 AGAINST THE BLOCKCHAIN
========================================================================
  contract        : 0x039E7A1234DD150522cb34a44Ca16056dC2B2daD
  anchored url    : https://www.youtube.com/watch?v=hdVZKS_cnn0
  on-chain hash   : 0x863cabb0b79b427642e0a0f9cc3d61f7249f113aaf22cd00e5f3639d189ffcf1
  recomputed hash : 0x863cabb0b79b427642e0a0f9cc3d61f7249f113aaf22cd00e5f3639d189ffcf1
========================================================================
  STATUS: VERIFIED
  Local record hashes to the value anchored on-chain.
========================================================================
```

### 3.10 Run the test suite

```bash
pytest -q
```

```
.........................................                                [100%]
41 passed in 1.63s
```

Fully offline, no network, models, keys or chain required. The full inventory of what
each test asserts, plus the live verification evidence, is in `TESTING.md`.

---

## 4. The tamper-evidence demo

This is the clearest proof that the record is tamper-evident.

**Step 1, confirm it is currently valid:**

```bash
python scripts/run_pipeline.py --verify 1
```
```
  STATUS: VERIFIED
```

**Step 2, edit the record.** Open `records/1.json` and change any character inside the
`"record"` object, one letter of the match URL is enough. Save.

**Step 3, verify again:**

```bash
python scripts/run_pipeline.py --verify 1
```
```
  on-chain hash   : 0x863cabb0b79b427642e0a0f9cc3d61f7249f113aaf22cd00e5f3639d189ffcf1
  recomputed hash : 0x66318fd75e4e16a22365d6fb3227f3664c6f85ec1f3458bb5d0efefe4157ebd4
========================================================================
  STATUS: TAMPERED
  Local record does NOT match the on-chain hash. It was altered after being anchored.
```

**The attack that does not work:** a determined attacker would also update the
`"record_hash"` field sitting next to the record, so the file looks internally
consistent. It still reports `TAMPERED`, verification compares against the **blockchain**,
never against the file's own copy of the hash. That case is covered by an automated test
(`test_verify_ignores_the_files_own_hash_field`).

**Step 4, restore.** Undo your edit to return the file to `VERIFIED`.

---

## 5. Optional HTTP API

Hosting is not required by the task; the CLI is the canonical demo. The same pipeline is
exposed over HTTP for interactive inspection:

```bash
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/api/docs

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Config and chain status |
| `POST /api/verify` | Upload a photo + `image_url`; runs the full pipeline |
| `GET /api/record/{id}` | Re-verify an anchored record against the chain |

The API and the CLI both call `app/pipeline.py`. There is no duplicated pipeline logic.

---

## 6. Troubleshooting

**`--image-url is required`**
Expected. Google Lens cannot search local bytes and we never upload your photo. Pass the
URL where the same image is already published.

**`RESULT: IMAGE URL MISMATCH`**
The URL shows a different face than your local file (cosine similarity below 0.9). This
is a safety guard: without it, the pipeline would anchor *your* face hash against a
search performed on *someone else's* photo, a permanently false record. Supply the
correct URL.

**`RESULT: NO SOCIAL MATCH`**
Working as intended. Lens searched the live index and found no social media page hosting
this image, so **nothing was written on-chain**. Fabricating a match to keep the demo
moving is exactly what the task forbids. Use a photo that is genuinely published on a
social platform.

**`RESULT: NO FACE`**
No detectable face, or the image is corrupt. Check the file opens in an image viewer.
Note some hosts (Wikimedia in particular) block automated downloads and return an HTML
error page instead of an image.

**`wallet ... has zero balance`**
Fund the address from the Coinbase faucet (§3.3). Confirm with `--health`.

**`SERPAPI_KEY not set in .env`**
Placeholder values from `.env.example` count as unset. Paste the real key.

**`Google Lens hasn't returned any results for this query`**
Lens could not fetch or match your URL. Confirm the URL opens the image directly in a
private browser window (not a page *containing* the image).

**`cannot reach RPC`**
`https://sepolia.base.org` may be briefly unavailable. Retry, or set `CHAIN_RPC_URL` in
`.env` to another Base Sepolia endpoint.

**InsightFace prints `Applied providers: ['CPUExecutionProvider']`**
Normal model-loading output, not an error.

---

## 7. Exit codes

Useful for scripting the demo.

| Code | Meaning |
|---|---|
| `0` | Success — anchored, or verification passed |
| `1` | Usage/config error (missing file, missing `--image-url`) |
| `2` | No face detected |
| `3` | No social match — nothing anchored (a legitimate outcome) |
| `4` | Verification returned `TAMPERED` |
| `5` | `--image-url` did not match the input photo |

---

## 8. Known limitations

Stated plainly rather than hidden. These are properties of the problem, not bugs.

1. **Reverse-image search matches images, not face identity.** Google does not offer
   face-identity search. The input photo must already exist online for anything to match.
   The face encoding binds the record to its input; it is not the search key.

2. **Social platform indexing is uneven.** Instagram and Facebook index poorly at the
   individual-post level. X/Twitter, Reddit, Pinterest and YouTube match far better.

3. **A public image URL is required.** Google Lens cannot accept local bytes, and the
   input photo is deliberately never auto-uploaded to an image host to work around that.

4. **Testnet, not mainnet.** Base Sepolia records are immutable and publicly verifiable,
   but the chain is not economically secured the way mainnet is. Moving to Base mainnet
   is a two-variable config change.

5. **One face per photo.** The largest detected face is used, and `face_count` is
   reported in the record so a crowded photo is visible as such.

6. **InsightFace `buffalo_l` is licensed for non-commercial research use.**

7. **SerpApi's free tier is capped** at 250 searches per month.

8. **A match is a claim, not a verdict.** The registry proves a specific claim existed
   unmodified at a specific block. It does not assert that the match is correct, which
   is why the contract is permissionless: it makes no truth claim.

---

## Privacy and responsible use

This pipeline can link a face to a social media identity and write the result somewhere
it can never be deleted.

- Only a hash of the face embedding is published, never the vector itself.
- The input photo is never uploaded anywhere by this code.
- A mismatched `--image-url` is refused before anything is anchored, so one person's face
  can never be bound to another person's search result.
- **Run it on your own photo, or on a public figure whose images are already widely
  published. Do not use it to deanonymise a private individual.**

Design rationale and the research behind each technical decision are documented
separately in `ARCHITECTURE.md`.

---

## Command reference

```bash
# status
python scripts/run_pipeline.py --health

# full pipeline
python scripts/run_pipeline.py <photo> --image-url <public-url-of-same-photo>

# verify an anchored record
python scripts/run_pipeline.py --verify <id>

# verify with no project code, no keys (for reviewers)
python scripts/verify_standalone.py <id> records/<id>.json

# deploy your own contract
python scripts/deploy_contract.py

# optional API
uvicorn app.main:app --reload
```
