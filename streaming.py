"""Cohere chat_stream consumption.

Single responsibility: call chat_stream, process every documented stream
event type, stream answer text to stdout, and accumulate tool plans and
tool calls. No orchestration logic.
"""

import time

import httpx

import ui

from config import MODEL
from logger import get_logger
from token_manager import (
    active_index, entry_count, get_client, note_request, note_success,
    rotate_on_error,
)
from tool_schemas import COHERE_TOOLS

log = get_logger("streaming")


def attr(obj, name, default=None):
    """Read a field from either an object attribute or a dict key."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


# ---------------------------------------------------------------------------
# Retry policy for transient API errors (429 rate limits, 5xx, network).
# Warriorx-style: bounded retries with backoff, never identical blind loops;
# every retry is logged and the user sees one short notice.
# ---------------------------------------------------------------------------

RETRY_MAX_ATTEMPTS = 6     # max wait-based retries once every credential entry failed
RETRY_BASE_DELAY = 2.0     # seconds, doubles per retry (5xx / network)
RETRY_MAX_DELAY = 60.0     # cap for any single backoff wait
RATE_LIMIT_WAIT = 61.0     # trial keys allow 20 calls/MINUTE -> wait out the
                           # full one-minute window before retrying a 429


def _is_retryable(exc: Exception) -> bool:
    """True for rate limits, server errors, timeouts, and network failures."""
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and (status == 429 or status >= 500):
        return True
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return True
    # httpx transport errors (ReadTimeout/ConnectTimeout/etc., connect/read
    # failures). httpx.TimeoutException is NOT a subclass of the builtin
    # TimeoutError/OSError, so it must be caught explicitly - otherwise a
    # client timeout would crash the turn instead of rotating credentials.
    if isinstance(exc, httpx.TransportError):
        return True
    return type(exc).__name__ in (
        "TooManyRequestsError", "InternalServerError",
        "ServiceUnavailableError", "GatewayTimeoutError",
        "ReadTimeout", "ConnectTimeout", "TimeoutException",
    )


def _is_rate_limit(exc: Exception) -> bool:
    """True for HTTP 429 / TooManyRequestsError."""
    return getattr(exc, "status_code", None) == 429 or type(exc).__name__ == "TooManyRequestsError"


def _retry_delay_seconds(exc: Exception, attempt: int) -> float:
    """Delay before the next attempt.

    Rate limits (429): honor Retry-After when the API sends one; otherwise
    wait out the full one-minute window (trial keys: 20 calls/minute).
    Short backoffs would just hit the same limit again.
    Other transient errors: exponential backoff capped at RETRY_MAX_DELAY.
    """
    if _is_rate_limit(exc):
        headers = getattr(exc, "headers", None) or {}
        if isinstance(headers, dict):
            raw = headers.get("retry-after") or headers.get("Retry-After")
            try:
                if raw is not None:
                    return max(1.0, min(float(raw), RETRY_MAX_DELAY))
            except (TypeError, ValueError):
                pass
        return RATE_LIMIT_WAIT
    return min(RETRY_BASE_DELAY * (2 ** (attempt - 1)), RETRY_MAX_DELAY)


def consume_stream(messages: list, allow_tools: bool = True):
    """Call chat_stream with credential rotation and retries.

    The client is obtained from token_manager on every attempt, so budget
    rotation (every REQUESTS_PER_TOKEN API calls) applies even mid-turn.
    On a retryable error (429 / 5xx / network) the agent rotates to the
    next {token, apiUrl} entry and retries IMMEDIATELY - no waiting - as
    long as a fresh entry exists. Only when every entry has failed since
    the last success does it fall back to waiting (rate-limit window /
    capped exponential backoff, bounded by RETRY_MAX_ATTEMPTS). Streams
    the final-answer text to stdout as it arrives.

    Returns (text, tool_plan, tool_calls, usage) where tool_calls is a list
    of dicts {"id", "type", "function": {"name", "arguments"}} and usage
    holds the token counts from the message-end event.
    """
    wait_attempts = 0
    while True:
        try:
            # Count the request first: when the active entry's budget is
            # exhausted this rotates to the next {token, apiUrl} entry, and
            # get_client() then builds the client for that fresh entry.
            note_request()
            co = get_client()
            result = _consume_once(co, messages, allow_tools)
            note_success()
            return result
        except Exception as exc:
            if not _is_retryable(exc):
                raise
            # Error-triggered rotation: a fresh credential entry is retried
            # immediately (no waiting). Only after every entry has failed
            # does the agent wait out a delay before retrying.
            if rotate_on_error():
                log.warning(
                    "retryable API error %s - rotated to credential entry %d/%d, "
                    "retrying immediately",
                    type(exc).__name__, active_index(), entry_count(),
                )
                ui.notice(
                    f"{type(exc).__name__} - switched to credential entry "
                    f"{active_index()}/{entry_count()}, retrying immediately"
                )
                continue
            wait_attempts += 1
            if wait_attempts >= RETRY_MAX_ATTEMPTS:
                raise
            delay = _retry_delay_seconds(exc, wait_attempts)
            log.warning(
                "retryable API error %s (all credential entries failed); "
                "waiting %.1fs (wait %d/%d)",
                type(exc).__name__, delay, wait_attempts, RETRY_MAX_ATTEMPTS - 1,
            )
            if _is_rate_limit(exc):
                ui.notice(
                    f"rate limit on every credential entry - waiting {delay:.0f}s "
                    f"for the next window (retry {wait_attempts}/{RETRY_MAX_ATTEMPTS - 1})"
                )
            else:
                ui.notice(
                    f"API {type(exc).__name__} - retry {wait_attempts}/{RETRY_MAX_ATTEMPTS - 1} in {delay:.0f}s"
                )
            time.sleep(delay)


def _parse_usage(usage_raw) -> dict:
    """Normalize the message-end usage payload into plain ints."""
    def _i(value):
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    tokens = attr(usage_raw, "tokens")
    billed = attr(usage_raw, "billed_units")
    return {
        "input_tokens": _i(attr(tokens, "input_tokens")),
        "output_tokens": _i(attr(tokens, "output_tokens")),
        "reasoning_tokens": _i(attr(tokens, "reasoning_tokens")),
        "cached_tokens": _i(attr(usage_raw, "cached_tokens")),
        "billed_input": _i(attr(billed, "input_tokens")),
        "billed_output": _i(attr(billed, "output_tokens")),
    }


def _consume_once(co, messages: list, allow_tools: bool = True):
    """Single (non-retried) chat_stream call and event accumulation.

    Handles both plain-text content and reasoning/'thinking' content
    (content-start with content.type='thinking', content-delta carrying
    the `thinking` field instead of `text`).

    Returns (text, plan, tool_calls, usage) where usage holds the token
    counts reported by the message-end event (zeros when absent).
    """
    text_parts = []
    thinking_parts = []
    plan_parts = []
    tool_calls = []      # accumulated tool calls, in start order
    tc_by_index = {}     # tool-call-delta events carry an index
    answer_prefix_printed = False
    in_thinking = False            # inside a thinking content block
    thinking_label_printed = False
    usage = {}                     # filled from the message-end event
    finish_reason = None

    stream_kwargs = {"model": MODEL, "messages": messages}
    if allow_tools:
        stream_kwargs["tools"] = COHERE_TOOLS
    try:
        stream = co.chat_stream(**stream_kwargs)
    except Exception:
        log.exception("chat_stream request failed (model=%s)", MODEL)
        raise
    for event in stream:
        if event is None:
            continue
        etype = attr(event, "type")
        message = attr(attr(event, "delta"), "message")

        if etype == "content-start":
            # content blocks are typed: 'text' or 'thinking'
            content_type = attr(attr(message, "content"), "type")
            in_thinking = (content_type == "thinking")

        elif etype == "content-delta":
            content = attr(message, "content")
            thinking_chunk = attr(content, "thinking")
            text_chunk = attr(content, "text")
            if thinking_chunk:
                # reasoning stream: shown dim/grey, separate from the answer
                if not thinking_label_printed:
                    print(ui.thinking_prefix(), end="", flush=True)
                    thinking_label_printed = True
                print(f"{ui.GREY}{thinking_chunk}{ui.RESET}", end="", flush=True)
                thinking_parts.append(thinking_chunk)
            elif text_chunk:
                if in_thinking:
                    in_thinking = False   # text arrived without a clean end
                print(ui.RESET, end="", flush=True)
                if not answer_prefix_printed:
                    print(ui.agent_prefix(), end="", flush=True)
                    answer_prefix_printed = True
                print(text_chunk, end="", flush=True)
                text_parts.append(text_chunk)

        elif etype == "content-end":
            if in_thinking:
                in_thinking = False
                print(ui.RESET + "\n", end="", flush=True)

        elif etype == "message-end":
            # Final event: carries finish_reason, an optional error, and
            # the token usage for this model call (fields live on the delta).
            delta = attr(event, "delta")
            finish_reason = attr(delta, "finish_reason")
            err = attr(delta, "error")
            if err:
                log.error("stream ended with API error: %s", err)
            usage_raw = attr(delta, "usage")
            if usage_raw is not None:
                usage = _parse_usage(usage_raw)

        elif etype == "tool-plan-delta":
            chunk = attr(message, "tool_plan")
            if chunk:
                plan_parts.append(chunk)

        elif etype == "tool-call-start":
            index = attr(event, "index", len(tool_calls))
            tc = attr(message, "tool_calls")
            fn = attr(tc, "function")
            new_tc = {
                "id": attr(tc, "id"),
                "type": attr(tc, "type", "function") or "function",
                "function": {
                    "name": attr(fn, "name"),
                    "arguments": attr(fn, "arguments", "") or "",
                },
            }
            tool_calls.append(new_tc)
            tc_by_index[index] = new_tc

        elif etype == "tool-call-delta":
            index = attr(event, "index", None)
            target = tc_by_index.get(index)
            if target is None and tool_calls:
                target = tool_calls[-1]
            chunk = attr(attr(attr(message, "tool_calls"), "function"), "arguments")
            if target is not None and chunk:
                target["function"]["arguments"] += chunk

    if answer_prefix_printed:
        print()  # newline after the streamed answer

    if thinking_parts:
        thinking_text = "".join(thinking_parts)
        log.debug("model thinking: %.2000s", thinking_text)

    log.debug(
        "model call finished | finish_reason=%s | usage=%s",
        finish_reason, usage or "n/a",
    )
    return "".join(text_parts), "".join(plan_parts), tool_calls, usage
