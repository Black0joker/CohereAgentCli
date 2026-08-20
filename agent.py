"""Mini AI Coding Agent - entry point (CLI REPL).

Single responsibility: bootstrap the agent and run the interactive REPL,
including named chat sessions (create/switch/remove) persisted in chats/.
All other concerns live in dedicated single-responsibility modules:

  config.py         - configuration constants (model, tokens file, rotation)
  token_manager.py  - tokens.json loading + credential rotation (every 18 requests)
  system_prompt.py  - the Warriorx-mindset system prompt
  tool_schemas.py   - Cohere function-calling tool schemas
  tool_engine.py    - adapter for the shared tool engine (module.py)
  tool_dispatch.py  - tool-call execution + retry discipline
  small_talk.py     - conversational-input detection (no tools for small talk)
  streaming.py      - chat_stream event consumption
  agent_loop.py     - the multi-step tool-use loop (run_turn)
  chat_store.py     - chat session persistence (chats/*.json)
  ui.py             - colors & appearance for all CLI output
  logger.py         - file-only logging (rotating logs/agent.log)

Run:  python agent.py
"""

import os
import sys

import ui

import chat_store

from agent_loop import run_turn
from config import MODEL
from logger import setup_logging
from system_prompt import SYSTEM_PROMPT
from token_manager import TokenConfigError, load_tokens, summary as credentials_summary
from tool_engine import set_workspace


HELP_TEXT = (
    f" {ui.CYAN}/new [name]{ui.RESET}     save the current chat (if it has history) and start a fresh one\n"
    f" {ui.CYAN}/chats{ui.RESET}          list saved chats (most recent first)\n"
    f" {ui.CYAN}/switch <ref>{ui.RESET}   switch to a saved chat - number from /chats or a name\n"
    f" {ui.CYAN}/remove <ref>{ui.RESET}   delete a saved chat - number from /chats or a name\n"
    f" {ui.CYAN}/help{ui.RESET}           show these commands\n"
    f" {ui.CYAN}exit | quit{ui.RESET}     leave"
)


def _fresh_messages() -> list:
    return [{"role": "system", "content": SYSTEM_PROMPT}]


def _first_user_text(messages: list) -> str:
    for m in messages:
        if isinstance(m, dict) and m.get("role") == "user":
            return m.get("content") or ""
    return ""


def _has_history(messages: list) -> bool:
    return any(isinstance(m, dict) and m.get("role") == "user" for m in messages)


def _save_current(messages: list, current_chat: str) -> str:
    """Auto-save the active session; returns the (possibly new) chat name.

    Unnamed sessions are named from their first user message at first save.
    Sessions without any user message are never persisted.
    """
    if not _has_history(messages):
        return current_chat
    if not current_chat:
        current_chat = chat_store.unique_name(
            chat_store.derive_name(_first_user_text(messages))
        )
    chat_store.save_chat(current_chat, messages)
    return current_chat


def _handle_command(line: str, messages: list, current_chat: str):
    """Handle a /slash command. Returns the (possibly replaced) (messages,
    current_chat) tuple."""
    parts = line.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd == "/help":
        print(HELP_TEXT)

    elif cmd == "/new":
        saved = _save_current(messages, current_chat)
        if saved:
            ui.chat_notice(f"saved chat '{saved}'")
        current_chat = chat_store.new_chat(arg) if arg else None
        messages = _fresh_messages()
        ui.chat_notice(
            f"new chat started" + (f": '{current_chat}'" if current_chat else "")
        )

    elif cmd == "/chats":
        ui.chat_list(chat_store.list_chats(), current_chat)

    elif cmd == "/switch":
        if not arg:
            ui.chat_notice("usage: /switch <number|name>")
        else:
            name = chat_store.resolve(arg, current_chat)
            if name is None:
                ui.chat_notice(f"no chat matching '{arg}' - see /chats")
            else:
                current_chat = _save_current(messages, current_chat)
                history = chat_store.load_chat(name)
                messages = _fresh_messages() + history
                current_chat = name
                ui.chat_notice(f"switched to '{name}' ({len(history)} messages)")

    elif cmd == "/remove":
        if not arg:
            ui.chat_notice("usage: /remove <number|name>")
        else:
            name = chat_store.resolve(arg, current_chat)
            if name is None:
                ui.chat_notice(f"no chat matching '{arg}' - see /chats")
            elif chat_store.remove_chat(name):
                if name == current_chat:
                    current_chat = None
                    messages = _fresh_messages()
                    ui.chat_notice(f"removed '{name}' - started a fresh chat")
                else:
                    ui.chat_notice(f"removed '{name}'")

    else:
        ui.chat_notice(f"unknown command '{cmd}' - /help for commands")

    return messages, current_chat


def main() -> None:
    # All diagnostics go to logs/agent.log; the console stays clean.
    log = setup_logging()
    log.info("session start | model=%s | workspace=%s", MODEL, os.getcwd())

    try:
        load_tokens()
    except TokenConfigError as e:
        log.critical("credential config error: %s", e)
        ui.error_message(str(e))
        sys.exit(1)
    log.info("credentials: %s", credentials_summary())

    # Pin the tool engine's workspace to the directory this agent runs in.
    set_workspace(os.getcwd())

    # The Cohere client lives in token_manager: it is (re)built per active
    # {token, apiUrl} entry and rotated every REQUESTS_PER_TOKEN API calls.
    messages = _fresh_messages()
    current_chat = None   # name of the active chat; None until first save

    ui.banner(MODEL, os.getcwd())

    while True:
        try:
            user_input = input(ui.user_prompt()).strip()
        except (EOFError, KeyboardInterrupt):
            current_chat = _save_current(messages, current_chat)
            ui.farewell("bye.")
            log.info("session end (eof/interrupt)")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            current_chat = _save_current(messages, current_chat)
            ui.farewell("bye.")
            log.info("session end (user exit)")
            break

        # Slash commands manage chat sessions - they never reach the model.
        if user_input.startswith("/"):
            messages, current_chat = _handle_command(user_input, messages, current_chat)
            log.info("chat command: %s (active=%s)", user_input[:200], current_chat)
            continue

        messages.append({"role": "user", "content": user_input})
        log.info("user turn (chat=%s): %s", current_chat or "-", user_input[:200])

        try:
            # run_turn streams the final answer to stdout as it arrives
            run_turn(messages)
            # Persist the turn so chats survive restarts
            current_chat = _save_current(messages, current_chat)
        except KeyboardInterrupt:
            ui.farewell("[interrupted]")
            log.warning("turn interrupted by user")
            break
        except Exception as e:
            # API / network / unexpected errors: full traceback goes to the
            # log file; the console gets a short message; session stays alive.
            log.exception("turn failed")
            ui.error_message(f"during turn: {e}")
            # Drop the unanswerable user message so history stays consistent
            messages.pop()
            continue


if __name__ == "__main__":
    main()
