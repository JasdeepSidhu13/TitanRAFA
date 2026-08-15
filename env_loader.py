"""Load .env file into os.environ via python-dotenv."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv as _dotenv_load

_ENV_LOADED = False


def load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE pairs from .env at repository root (once per process).

    Uses override=True so .env values replace stale shell exports.
    """
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    env_path = path or Path(__file__).resolve().parent / ".env"
    if env_path.is_file():
        _dotenv_load(env_path, override=True)
    _ENV_LOADED = True
