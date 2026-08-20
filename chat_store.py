"""Chat session persistence.

Single responsibility: create, list, load, save, and remove named chat
sessions stored as JSON files under the chats/ directory. The system
prompt message is never persisted - it is re-inserted by the caller on
load. No agent-loop logic.
"""

import json
import os
import re
from datetime import datetime

from logger import get_logger

log = get_logger("chats")

CHAT_DIR = "chats"
MAX_NAME_LEN = 60


def _ensure_dir() -> None:
    os.makedirs(CHAT_DIR, exist_ok=True)


def sanitize_name(name: str) -> str:
    """Turn arbitrary text into a safe, non-empty chat/file name."""
    name = re.sub(r"[^\w\s-]", "", str(name), flags=re.UNICODE)
    name = " ".join(name.split()).strip().replace(" ", "-")
    if not name:
        return "chat"
    return name[:MAX_NAME_LEN].rstrip("-") or "chat"


def derive_name(first_user_text: str) -> str:
    """Auto-name a chat from its first user message (first few words)."""
    words = " ".join(str(first_user_text).split())[:48].strip()
    return sanitize_name(words) if words else "chat"


def _path(name: str) -> str:
    return os.path.join(CHAT_DIR, f"{name}.json")


def _unique_name(base: str) -> str:
    """Append -2, -3, ... until the name is unused."""
    name = base
    i = 2
    while os.path.exists(_path(name)):
        name = f"{base}-{i}"
        i += 1
    return name


def unique_name(base: str) -> str:
    """Public wrapper: sanitize a base name and make it unique."""
    return _unique_name(sanitize_name(base))


def chat_exists(name: str) -> bool:
    return os.path.isfile(_path(name))


def list_chats() -> list:
    """Return [{name, updated, messages}] sorted by most recently updated."""
    _ensure_dir()
    chats = []
    for fname in os.listdir(CHAT_DIR):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(CHAT_DIR, fname), "r", encoding="utf-8") as f:
                data = json.load(f)
            chats.append({
                "name": data.get("name", fname[:-5]),
                "updated": data.get("updated", ""),
                "messages": data.get("messages", []),
            })
        except (json.JSONDecodeError, OSError) as e:
            log.warning("skipping unreadable chat file %s: %s", fname, e)
    chats.sort(key=lambda c: c["updated"], reverse=True)
    return chats


def load_chat(name: str) -> list:
    """Return the stored non-system messages for a chat (empty if missing)."""
    if not chat_exists(name):
        return []
    with open(_path(name), "r", encoding="utf-8") as f:
        data = json.load(f)
    messages = data.get("messages", [])
    return [m for m in messages if isinstance(m, dict) and m.get("role") != "system"]


def save_chat(name: str, messages: list) -> str:
    """Persist a chat and return its final name.

    `name` may be empty/None for a not-yet-named session only when a name
    was derived beforehand; the caller is expected to pass the resolved
    name. The system message is stripped before writing. The write is
    atomic (temp file + rename).
    """
    _ensure_dir()
    clean = [m for m in messages if isinstance(m, dict) and m.get("role") != "system"]
    now = datetime.now().isoformat(timespec="seconds")
    payload = {"name": name, "updated": now, "messages": clean}
    tmp = _path(name) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _path(name))
    return name


def new_chat(name: str) -> str:
    """Create a new empty chat and return its unique name."""
    base = sanitize_name(name) if name else f"chat-{datetime.now():%Y%m%d-%H%M%S}"
    final = _unique_name(base)
    save_chat(final, [])
    log.info("chat created: %s", final)
    return final


def remove_chat(name: str) -> bool:
    """Delete a chat file. Returns True when something was removed."""
    if not chat_exists(name):
        return False
    os.remove(_path(name))
    log.info("chat removed: %s", name)
    return True


def resolve(ref: str, active: str = None) -> str:
    """Resolve a user reference (1-based list position or name) to a chat name.

    Returns the chat name, or None when nothing matches.
    """
    ref = str(ref).strip()
    chats = list_chats()
    if ref.isdigit():
        idx = int(ref)
        if 1 <= idx <= len(chats):
            return chats[idx - 1]["name"]
        return None
    name = sanitize_name(ref)
    if chat_exists(name):
        return name
    # Fall back to a unique prefix match on the original reference
    matches = [c["name"] for c in chats if c["name"].lower().startswith(ref.lower())]
    if len(matches) == 1:
        return matches[0]
    return None
