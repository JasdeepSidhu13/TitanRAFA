"""Load .env file into os.environ without external dependencies."""

from __future__ import annotations

import os
from pathlib import Path

_ENV_LOADED = False


def load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE pairs from .env at repository root (once per process)."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    env_path = path or Path(__file__).resolve().parent / ".env"
    if not env_path.is_file():
        _ENV_LOADED = True
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
    _ENV_LOADED = True
