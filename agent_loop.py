"""Agent turn execution (the multi-step tool-use loop).

Single responsibility: orchestrate one user turn - stream model responses,
execute requested tools, replay results, apply Warriorx retry discipline,
and stop at the final answer or the step budget.
"""

import json
import time

import ui

from config import MAX_STEPS
from logger import get_logger
from small_talk import is_conversational
from streaming import consume_stream
from tool_dispatch import dispatch_tool, inject_retry_guidance, is_error_result

log = get_logger("loop")


def run_turn(co, messages: list) -> str:
    """Run one user turn with streaming: loop tool calls until the model
    produces a final answer (streamed to stdout as it arrives).

    Returns the final assistant text. Appends all intermediate messages to
    `messages` so multi-turn conversation memory is preserved.
    """
    # Signature -> last result, to detect identical retries of failed calls
    seen_calls = {}

    # Pure small talk (e.g. "hi") must get a direct answer - no tools.
    last_user = ""
    for m in reversed(messages):
        if isinstance(m, dict) and m.get("role") == "user":
            last_user = m.get("content", "") or ""
            break
    allow_tools = not is_conversational(last_user)

    # Accumulated token consumption across every model call in this turn
    usage_total = {}

    def _report_usage(steps: int) -> None:
        """Show + log the token consumption for the completed turn."""
        if not usage_total:
            return
        ui.turn_usage(usage_total)
        log.info(
            "turn usage: steps=%d input=%d output=%d reasoning=%d cached=%d",
            steps,
            usage_total.get("input_tokens", 0),
            usage_total.get("output_tokens", 0),
            usage_total.get("reasoning_tokens", 0),
            usage_total.get("cached_tokens", 0),
        )

    for step in range(1, MAX_STEPS + 1):
        text, plan, tool_calls, usage = consume_stream(
            co, messages,
            # small talk: omit the tool schemas entirely so tool calls are impossible
            allow_tools=allow_tools if step == 1 else True,
        )
        for key, value in usage.items():
            usage_total[key] = usage_total.get(key, 0) + value

        if not tool_calls:
            # Direct answer - already streamed to stdout
            messages.append({"role": "assistant", "content": text})
            _report_usage(step)
            return text

        # --- tool-calling branch ---
        ui.step_header(step, plan)

        # Normalize arguments: zero-argument tools may stream no argument
        # deltas, leaving an empty string. The API requires a stringified
        # JSON object when the assistant message is replayed in history.
        for tc in tool_calls:
            raw = tc["function"]["arguments"]
            try:
                parsed = json.loads(raw or "{}")
            except json.JSONDecodeError:
                parsed = {}
            if not isinstance(parsed, dict):
                parsed = {}
            tc["function"]["arguments"] = json.dumps(parsed, ensure_ascii=False)

        # Rebuild the assistant message (plain-dict form) for history.
        # NOTE: `tool_plan` is kept for display only; this model rejects it
        # inside replayed history messages.
        messages.append({
            "role": "assistant",
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["function"]["name"],
                        "arguments": tc["function"]["arguments"],
                    },
                }
                for tc in tool_calls
            ],
        })

        for tc in tool_calls:
            name = tc["function"]["name"]
            arguments = json.loads(tc["function"]["arguments"])  # always valid now

            # Show the tool BEFORE executing
            log.debug("tool call: %s %s", name, tc["function"]["arguments"])
            ui.tool_start(name, tc["function"]["arguments"])

            started = time.perf_counter()
            try:
                result_str = dispatch_tool(name, arguments)
            except Exception as exc:  # never let one tool crash the loop
                log.exception("tool dispatch crashed: %s", name)
                result_str = json.dumps({
                    "status": "error",
                    "tool": name,
                    "result": {"error_msg": f"Unhandled exception: {exc}"},
                })

            # Warriorx discipline: an identical retry of a failed call gets the
            # original error plus an explicit directive to change strategy.
            call_sig = (name, tc["function"]["arguments"])
            prev_result = seen_calls.get(call_sig)
            if prev_result is not None and is_error_result(prev_result):
                result_str = inject_retry_guidance(result_str)
            seen_calls[call_sig] = result_str

            # Show the tool outcome AFTER executing
            ui.tool_end(name, result_str, time.perf_counter() - started)

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result_str,
            })

    # Step budget exhausted
    log.warning("step budget exhausted (%d steps) without a final answer", MAX_STEPS)
    fallback = "Reached the maximum number of tool steps without a final answer. Please refine the request."
    messages.append({"role": "assistant", "content": fallback})
    ui.fallback_answer(fallback)
    _report_usage(MAX_STEPS)
    return fallback
