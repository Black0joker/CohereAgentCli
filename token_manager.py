"""Credential rotation.

Single responsibility: load [{token, apiUrl}] entries from tokens.json and
rotate to the next entry after REQUESTS_PER_TOKEN API calls - or immediately
when an API call fails (e.g. a 429 rate limit). Owns the cohere.ClientV2
lifecycle (rebuilt automatically on rotation). No agent-loop logic.
"""

import json
import os
import threading

import cohere

from config import TOKENS_FILE, REQUESTS_PER_TOKEN, CLIENT_TIMEOUT
from logger import get_logger

log = get_logger("tokens")

_lock = threading.Lock()
_entries = []                       # [{"token": str, "apiUrl": str | None}]
_index = 0                          # active entry index
_remaining = REQUESTS_PER_TOKEN     # API calls left for the active entry
_client = None                      # cached ClientV2 for the active entry
_failed_streak = 0                  # entries failed in a row since last success


class TokenConfigError(Exception):
    """Raised when tokens.json is missing, malformed, or has no entries."""


def load_tokens(path: str = TOKENS_FILE) -> list:
    """Load and validate [{token, apiUrl}] credential entries from JSON."""
    global _entries, _index, _remaining, _client, _failed_streak
    if not os.path.exists(path):
        raise TokenConfigError(
            f"{path} not found. Create it as: "
            '[{"token": "your_api_key", "apiUrl": "https://api.cohere.com"}]'
        )
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise TokenConfigError(f"{path} is not valid JSON: {e}")
    if not isinstance(data, list) or not data:
        raise TokenConfigError(f"{path} must be a non-empty JSON array")

    entries = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise TokenConfigError(f"{path} entry {i} must be an object")
        token = str(item.get("token") or "").strip()
        if not token:
            raise TokenConfigError(f"{path} entry {i} is missing 'token'")
        api_url = str(item.get("apiUrl") or "").strip() or None
        entries.append({"token": token, "apiUrl": api_url})

    with _lock:
        _entries = entries
        _index = 0
        _remaining = REQUESTS_PER_TOKEN
        _client = None
        _failed_streak = 0
    return entries


def _build_client(entry: dict) -> "cohere.ClientV2":
    """Build a ClientV2 for one entry (apiUrl '' -> SDK default endpoint).

    Every request uses CLIENT_TIMEOUT seconds; a request that exceeds the
    timeout raises an httpx timeout error, which the retry layer treats as
    a failure and rotates to the next credential entry.
    """
    kwargs = {"api_key": entry["token"], "timeout": CLIENT_TIMEOUT}
    if entry["apiUrl"]:
        kwargs["base_url"] = entry["apiUrl"]
    return cohere.ClientV2(**kwargs)


def get_client() -> "cohere.ClientV2":
    """Return the ClientV2 for the active entry (cached until rotation)."""
    global _client
    with _lock:
        if not _entries:
            raise TokenConfigError("tokens not loaded - call load_tokens() first")
        if _client is None:
            _client = _build_client(_entries[_index])
        return _client


def note_request() -> None:
    """Count one API request against the active entry's budget.

    Must be called BEFORE get_client(): when the active entry's budget
    (REQUESTS_PER_TOKEN) is already exhausted, this rotates to the next
    entry (wrapping around) and drops the cached client, so the current
    request is made with the fresh token/apiUrl. Each entry therefore
    serves exactly REQUESTS_PER_TOKEN requests.
    """
    global _remaining, _index, _client
    with _lock:
        if not _entries:
            return
        if _remaining <= 0:
            if len(_entries) > 1:
                _index = (_index + 1) % len(_entries)
                _client = None
                log.info(
                    "rotated to credential entry %d/%d (budget: %d requests)",
                    _index + 1, len(_entries), REQUESTS_PER_TOKEN,
                )
            _remaining = REQUESTS_PER_TOKEN
        _remaining -= 1


def rotate_on_error() -> bool:
    """Force rotation to the next entry after a failed API call.

    Returns True when a fresh entry was activated (the caller should retry
    immediately with the new token/apiUrl). Returns False when rotation is
    pointless: only one entry is configured, or every entry has already
    failed since the last success (the caller should wait before retrying).
    """
    global _failed_streak, _index, _remaining, _client
    with _lock:
        if len(_entries) <= 1 or _failed_streak >= len(_entries) - 1:
            return False
        _failed_streak += 1
        _index = (_index + 1) % len(_entries)
        _remaining = REQUESTS_PER_TOKEN
        _client = None
        log.info(
            "error-triggered rotation: switched to entry %d/%d (failed streak: %d)",
            _index + 1, len(_entries), _failed_streak,
        )
        return True


def note_success() -> None:
    """Record a successful API call (resets the failed-entry streak)."""
    global _failed_streak
    with _lock:
        _failed_streak = 0


def entry_count() -> int:
    """Number of loaded credential entries."""
    with _lock:
        return len(_entries)


def active_index() -> int:
    """1-based index of the active credential entry (0 when unloaded)."""
    with _lock:
        return _index + 1 if _entries else 0


def summary() -> str:
    """Short human-readable description of the loaded credentials."""
    with _lock:
        if not _entries:
            return "no credentials loaded"
        plural = "entry" if len(_entries) == 1 else "entries"
        return f"{len(_entries)} credential {plural}, rotating every {REQUESTS_PER_TOKEN} requests"
