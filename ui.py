"""User-interface styling for the CLI.

Single responsibility: all colors and appearance (banner, prompts, streamed
answers, tool execution display, log lines). No agent logic.

Colors are ANSI-based and disable automatically when stdout is not a TTY
or NO_COLOR is set, so piped/captured output stays clean.
"""

import json
import os
import sys


# ---------------------------------------------------------------------------
# ANSI color support (graceful fallback when colors are unavailable)
# ---------------------------------------------------------------------------

def _colors_enabled() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
        return False
    if os.name == "nt":
        # Enable VT/ANSI processing on Windows 10+ consoles
        os.system("")
    return True


COLORS = _colors_enabled()


def _c(code: str) -> str:
    return f"\033[{code}m" if COLORS else ""


RESET = _c("0")
BOLD = _c("1")
DIM = _c("2")

RED = _c("31")
GREEN = _c("32")
YELLOW = _c("33")
BLUE = _c("34")
MAGENTA = _c("35")
CYAN = _c("36")
GREY = _c("90")


# ---------------------------------------------------------------------------
# Glyph sets: fancy Unicode when attached to a real terminal, ASCII-safe
# fallback otherwise (piped output, limited code pages).
# ---------------------------------------------------------------------------

def _glyphs(fancy: bool) -> dict:
    if fancy:
        return {
            "banner": "\u2550", "prompt": "\u276f", "step": "\u25c6",
            "pipe": "\u2502", "tool": "\u2699", "ok": "\u2713",
            "fail": "\u2717", "ellipsis": "\u2026", "usage": "\u25c8",
        }
    return {
        "banner": "=", "prompt": ">", "step": "*",
        "pipe": "|", "tool": ">", "ok": "OK", "fail": "ERR",
        "ellipsis": "...", "usage": "#",
    }


G = _glyphs(COLORS)


# ---------------------------------------------------------------------------
# Small text helpers
# ---------------------------------------------------------------------------

def _clip(text: str, limit: int = 80) -> str:
    """Collapse whitespace and truncate to a single short line."""
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + G["ellipsis"]


# ---------------------------------------------------------------------------
# Banner & prompts
# ---------------------------------------------------------------------------

def banner(model: str, workspace: str) -> None:
    line = G["banner"] * 62
    print(f"{CYAN}{line}{RESET}")
    print(f"{CYAN}{BOLD} Mini AI Coding Agent{RESET}  {GREY}(Cohere {model}){RESET}")
    print(f" {GREY}Workspace:{RESET} {workspace}")
    print(f" {GREY}Type your request. '/help' for chat commands, 'exit' to leave.{RESET}")
    print(f"{CYAN}{line}{RESET}")


def user_prompt() -> str:
    return f"\n{CYAN}{BOLD}you {G['prompt']}{RESET} "


def agent_prefix() -> str:
    return f"\n{GREEN}{BOLD}agent {G['prompt']}{RESET} "


def thinking_prefix() -> str:
    """Label printed before streamed model thinking (dim grey, distinct
    from the final answer)."""
    return f"\n{GREY}{DIM}  {G['pipe']} thinking{RESET}{GREY}: "


def farewell(text: str) -> None:
    print(f"\n{GREY}{text}{RESET}")


def error_message(text: str) -> None:
    print(f"\n{RED}{BOLD}error:{RESET} {RED}{_clip(text, 400)}{RESET}")


def notice(text: str) -> None:
    """Short transient status line (e.g. retry notices). Not logging."""
    print(f"\n{YELLOW}{DIM}  {G['ellipsis']} {text}{RESET}", flush=True)


# ---------------------------------------------------------------------------
# Chat sessions
# ---------------------------------------------------------------------------

def chat_notice(text: str) -> None:
    """Feedback line for chat create/switch/remove operations."""
    print(f"\n{CYAN}{DIM}  {G['usage']} {text}{RESET}", flush=True)


def chat_list(chats: list, active: str = None) -> None:
    """Display saved chats with 1-based positions; mark the active one."""
    if not chats:
        print(f"\n{GREY}  no saved chats yet - use /new to start one{RESET}")
        return
    print()
    for i, chat in enumerate(chats, 1):
        marker = f"{GREEN}{BOLD}*{RESET} " if chat["name"] == active else "  "
        turns = len(chat.get("messages", []))
        stamp = chat.get("updated", "")[:16].replace("T", " ")
        print(
            f"{marker}{GREY}{i:>2}){RESET} {BOLD}{chat['name']}{RESET}"
            f" {GREY}{G['pipe']} {turns} msgs {G['pipe']} {stamp}{RESET}"
        )


# ---------------------------------------------------------------------------
# Agent loop display
# ---------------------------------------------------------------------------

def step_header(step: int, plan: str) -> None:
    plan_txt = f"  {GREY}{G['pipe']}{RESET} {_clip(plan, 120)}" if plan else ""
    print(f"\n{MAGENTA}{BOLD}  {G['step']} step {step}{RESET}{plan_txt}")


def tool_start(name: str, arguments_str: str) -> None:
    """Printed BEFORE a tool executes."""
    args = _clip(arguments_str, 160)
    print(f"{YELLOW}    {G['tool']} {BOLD}{name}{RESET}{GREY} {args}{RESET}", flush=True)


def tool_end(name: str, result_str: str, elapsed: float) -> None:
    """Printed AFTER a tool executes, with a compact outcome summary."""
    ok, summary = _summarize_result(result_str)
    timing = f"{GREY}({elapsed:.2f}s){RESET}"
    if ok:
        print(f"    {GREEN}{G['ok']}{RESET} {GREY}{summary}{RESET} {timing}", flush=True)
    else:
        print(f"    {RED}{BOLD}{G['fail']}{RESET} {RED}{summary}{RESET} {timing}", flush=True)


def turn_usage(usage: dict) -> None:
    """Compact token-consumption summary at the end of a turn."""
    if not usage:
        return
    inp = usage.get("input_tokens", 0)
    out = usage.get("output_tokens", 0)
    reasoning = usage.get("reasoning_tokens", 0)
    cached = usage.get("cached_tokens", 0)
    parts = [f"{inp:,} in", f"{out:,} out"]
    if reasoning:
        parts.append(f"{reasoning:,} reasoning")
    if cached:
        parts.append(f"{cached:,} cached")
    print(f"\n{GREY}{DIM}  {G['usage']} tokens: {' | '.join(parts)}{RESET}", flush=True)


# ---------------------------------------------------------------------------
# Log lines (used by the tool engine adapter)
# ---------------------------------------------------------------------------

def log(level: str, msg: str) -> None:
    color = {"info": BLUE, "warn": YELLOW, "error": RED}.get(level, GREY)
    print(f"  {color}[{level}]{RESET} {GREY}{_clip(msg, 200)}{RESET}")


# ---------------------------------------------------------------------------
# Tool-result summarization
# ---------------------------------------------------------------------------

def _summarize_result(result_str: str):
    """Return (ok: bool, short_summary: str) for a serialized tool envelope."""
    try:
        data = json.loads(result_str)
    except json.JSONDecodeError:
        return True, _clip(result_str)
    if not isinstance(data, dict):
        return True, _clip(result_str)

    result = data.get("result") if isinstance(data.get("result"), dict) else {}

    if data.get("status") == "error":
        msg = result.get("error_msg") or ""
        if not msg and isinstance(data.get("error"), dict):
            msg = data["error"].get("message", "")
        return False, _clip(msg or "error")

    if "entries" in result:
        return True, f"{len(result['entries'])} entries"
    if "matches" in result:
        return True, f"{len(result['matches'])} matches"
    if isinstance(result.get("results"), list):
        return True, f"{len(result['results'])} results"
    if "content" in result and "total_lines" in result:
        return True, f"lines {result.get('start_line')}-{result.get('end_line')} of {result.get('total_lines')}"
    if "replacements_made" in result:
        return True, f"{result['replacements_made']} replacement ({result.get('match_type', '?')})"
    if "returncode" in result:
        rc = result["returncode"]
        if rc == 0:
            return True, "exit code 0"
        detail = _clip((result.get("stderr") or result.get("stdout") or ""), 60)
        return False, f"exit code {rc}" + (f" {G['pipe']} {detail}" if detail else "")
    if "background_id" in result:
        return True, f"background id: {result['background_id']}"
    if "status_code" in result:
        sc = result["status_code"]
        return (200 <= sc < 300), f"HTTP {sc}"
    if "path" in result:
        return True, f"path: {result['path']}"
    if "mode" in result:
        return True, f"mode: {result['mode']}"
    return True, "ok"
