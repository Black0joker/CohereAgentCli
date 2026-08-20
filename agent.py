"""Mini AI Coding Agent - entry point (CLI REPL).

Single responsibility: bootstrap the agent and run the interactive REPL.
All other concerns live in dedicated single-responsibility modules:

  config.py         - configuration constants (model, step budget, tokens file, rotation)
  token_manager.py  - tokens.json loading + credential rotation (every 18 requests)
  system_prompt.py  - the Warriorx-mindset system prompt
  tool_schemas.py   - Cohere function-calling tool schemas
  tool_engine.py    - adapter for the shared tool engine (module.py)
  tool_dispatch.py  - tool-call execution + retry discipline
  small_talk.py     - conversational-input detection (no tools for small talk)
  streaming.py      - chat_stream event consumption
  agent_loop.py     - the multi-step tool-use loop (run_turn)
  ui.py             - colors & appearance for all CLI output
  logger.py         - file-only logging (rotating logs/agent.log)

Run:  python agent.py
"""

import os
import sys

import ui

from agent_loop import run_turn
from config import MODEL
from logger import setup_logging
from system_prompt import SYSTEM_PROMPT
from token_manager import TokenConfigError, load_tokens, summary as credentials_summary
from tool_engine import set_workspace


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
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    ui.banner(MODEL, os.getcwd())

    while True:
        try:
            user_input = input(ui.user_prompt()).strip()
        except (EOFError, KeyboardInterrupt):
            ui.farewell("bye.")
            log.info("session end (eof/interrupt)")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            ui.farewell("bye.")
            log.info("session end (user exit)")
            break

        messages.append({"role": "user", "content": user_input})
        log.info("user turn: %s", user_input[:200])

        try:
            # run_turn streams the final answer to stdout as it arrives
            run_turn(messages)
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
