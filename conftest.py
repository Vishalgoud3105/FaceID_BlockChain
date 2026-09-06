import sys
from pathlib import Path

# Make `app` importable when pytest is invoked as bare `pytest`, not just
# `python -m pytest` (which puts the CWD on sys.path for you).
sys.path.insert(0, str(Path(__file__).resolve().parent))
