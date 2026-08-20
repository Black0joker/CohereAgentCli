"""Configuration constants for the mini AI coding agent.

Single responsibility: central, tunable settings. No logic.
"""

import os
import sys


def _app_dir() -> str:
    """Directory of the running application.

    Frozen (PyInstaller exe): the directory containing the exe, so
    tokens.json travels with the executable regardless of the caller's
    working directory. Running from source: this file's directory.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


APP_DIR = _app_dir()

MODEL = "command-a-reasoning-08-2025"
TOKENS_FILE = os.path.join(APP_DIR, "tokens.json")  # [{token, apiUrl}] entries
REQUESTS_PER_TOKEN = 18       # rotate to the next entry after this many API calls
CLIENT_TIMEOUT = 5.0          # seconds; a request exceeding this triggers rotation
