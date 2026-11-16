"""Application configuration, loaded from a single YAML file.

Settings live in config.yaml (path overridable via the CONFIG_FILE env var,
which is the only env var the app itself reads). The file holds all app settings
plus a preseeded users list. See config.example.yaml.

Infra paths (DATA_DIR, HF_HOME) remain environment-driven because they describe
where the container stores things, not application behaviour.
"""

import logging
import os
from pathlib import Path

import yaml

logger = logging.getLogger("transcryber.config")

CONFIG_FILE = os.getenv("CONFIG_FILE", "config.yaml")


def _load_raw() -> dict:
    path = Path(CONFIG_FILE)
    if path.is_file():
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        logger.info("Loaded configuration from %s", path.resolve())
        return data
    logger.warning(
        "Config file '%s' not found — using built-in defaults (SQLite, no "
        "preseeded users, ephemeral SECRET_KEY).",
        path,
    )
    return {}


_raw = _load_raw()

# --- Paths (infra, env-driven) ---------------------------------------------
DATA_DIR = Path(
    _raw.get("data_dir") or os.getenv("DATA_DIR") or (Path(__file__).resolve().parent.parent / "data")
)
DATA_DIR.mkdir(parents=True, exist_ok=True)

# --- Core ------------------------------------------------------------------
SECRET_KEY = _raw.get("secret_key") or None  # falsy -> main.py generates ephemeral
DATABASE_URL = _raw.get("database_url") or f"sqlite:///{DATA_DIR / 'transcryber.db'}"

# --- Whisper ---------------------------------------------------------------
_whisper = _raw.get("whisper") or {}
WHISPER_MODEL = _whisper.get("model", "small")
WHISPER_DEVICE = _whisper.get("device", "cpu")
WHISPER_COMPUTE_TYPE = _whisper.get("compute_type", "int8")
WHISPER_BEAM_SIZE = int(_whisper.get("beam_size", 5))

# --- HuggingFace -----------------------------------------------------------
_hf = _raw.get("huggingface") or {}
HF_TOKEN = _hf.get("token") or None

# --- Preseeded users -------------------------------------------------------
# List of {username, password_hash}; usernames plaintext, passwords bcrypt hashes.
USERS = _raw.get("users") or []
