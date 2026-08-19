"""Mini AI Coding Agent - entry point (CLI REPL).

Single responsibility: bootstrap the agent and run the interactive REPL.
All other concerns live in dedicated single-responsibility modules:

  config.py         - configuration constants (model, step budget, env file)
  env_loader.py     - .env parsing (COHERE_API_KEY)
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

import cohere

import ui

from agent_loop import run_turn
from config import MODEL
from env_loader import load_env
from logger import setup_logging
from system_prompt import SYSTEM_PROMPT
from tool_engine import set_workspace


def main() -> None:
    # All diagnostics go to logs/agent.log; the console stays clean.
    log = setup_logging()
    log.info("session start | model=%s | workspace=%s", MODEL, os.getcwd())

    api_key = load_env().get("COHERE_API_KEY") or os.environ.get("COHERE_API_KEY")
    if not api_key:
        log.critical("COHERE_API_KEY not found in .env or environment")
        ui.error_message("COHERE_API_KEY not found in .env or environment.")
        sys.exit(1)

    # Pin the tool engine's workspace to the directory this agent runs in.
    set_workspace(os.getcwd())

    co = cohere.ClientV2(api_key=api_key)
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
            run_turn(co, messages)
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
