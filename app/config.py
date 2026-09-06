"""Environment configuration.

Loaded once at import. Nothing here raises on a missing value — the pipeline
reports what is missing at /api/health instead of refusing to start, so you can
boot the app and see exactly which key is absent.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _env(name: str, default: str = "") -> str:
    """Read an env var, treating .env.example placeholders as unset.

    Copying .env.example to .env leaves strings like `your_..._api_key` in
    place. Those are non-empty, so a naive truthiness check reports the key as
    present and the failure only surfaces on the first real API call. Catch it
    here instead.
    """
    value = os.getenv(name, default).strip()
    lowered = value.lower()
    if lowered.startswith("your_") or lowered.startswith("0xyour_"):
        return ""
    return value


RECORDS_DIR = BASE_DIR / "records"
RECORDS_DIR.mkdir(parents=True, exist_ok=True)

CONTRACT_ARTIFACT = BASE_DIR / "contracts" / "FaceMatchRegistry.json"
CONTRACT_SOURCE = BASE_DIR / "contracts" / "FaceMatchRegistry.sol"

# --- Reverse image search ---
SERPAPI_KEY = _env("SERPAPI_KEY")

# --- Chain ---
CHAIN_RPC_URL = _env("CHAIN_RPC_URL", "https://sepolia.base.org")
CHAIN_ID = int(os.getenv("CHAIN_ID", "84532"))
CHAIN_NAME = os.getenv("CHAIN_NAME", "Base Sepolia").strip()
EXPLORER_TX_URL = os.getenv("EXPLORER_TX_URL", "https://sepolia.basescan.org/tx/").strip()
WALLET_PRIVATE_KEY = _env("WALLET_PRIVATE_KEY")
CONTRACT_ADDRESS = _env("CONTRACT_ADDRESS")

# --- Tuning ---
MIN_FACE_SCORE = float(os.getenv("MIN_FACE_SCORE", "0.5"))

SOLC_VERSION = "0.8.24"


def missing_keys() -> list[str]:
    """Which required settings are absent. Surfaced by /api/health."""
    missing = []
    if not SERPAPI_KEY:
        missing.append("SERPAPI_KEY")
    if not WALLET_PRIVATE_KEY:
        missing.append("WALLET_PRIVATE_KEY")
    if not CONTRACT_ADDRESS and not _artifact_address():
        missing.append("CONTRACT_ADDRESS (run scripts/deploy_contract.py)")
    return missing


def _artifact_address() -> str:
    """The deploy script records the address in the committed artifact, so an
    empty CONTRACT_ADDRESS in .env is not actually a missing configuration."""
    try:
        import json

        return json.loads(CONTRACT_ARTIFACT.read_text(encoding="utf-8")).get("address") or ""
    except Exception:
        return ""
