"""Environment file loading.

Single responsibility: parse a simple KEY=VALUE .env file (no external
dependency required). Used to obtain the Cohere API key.
"""

import os

from config import ENV_FILE


def load_env(path: str = ENV_FILE) -> dict:
    """Parse a simple KEY=VALUE .env file."""
    env = {}
    if not os.path.exists(path):
        return env
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env
