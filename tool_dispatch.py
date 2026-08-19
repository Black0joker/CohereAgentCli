"""Tool-call dispatch and retry discipline.

Single responsibility: execute one model-issued tool call and enforce the
Warriorx error-handling rules (error detection, identical-retry warnings).
"""

import json

from tool_engine import execute_tool


def dispatch_tool(name: str, arguments: dict) -> str:
    """Execute one tool call and return its result as a JSON string."""
    # All tools are handled by the shared tool engine in module.py
    return json.dumps(execute_tool(name, arguments), ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# Warriorx discipline helpers (error handling & recovery mindset)
# ---------------------------------------------------------------------------

def is_error_result(result_str: str) -> bool:
    """Return True when a serialized tool-result envelope indicates failure."""
    try:
        data = json.loads(result_str)
    except json.JSONDecodeError:
        return False
    if not isinstance(data, dict):
        return False
    if data.get("status") == "error":
        return True
    inner = data.get("result")
    if isinstance(inner, dict) and (inner.get("error_msg") or inner.get("error_type")):
        return True
    if isinstance(data.get("error"), dict):
        return True
    return False


def inject_retry_guidance(result_str: str) -> str:
    """Flag an identical retry of a previously failed call.

    Warriorx rule: retries must change something (input, strategy, or tool).
    The model gets the original error plus an explicit corrective directive.
    """
    try:
        data = json.loads(result_str)
    except json.JSONDecodeError:
        return result_str
    if isinstance(data, dict):
        data["warning"] = (
            "Identical retry detected: this exact call already failed. "
            "Never repeat an identical failing call. Change the input, re-read the "
            "target, or switch to a different tool/strategy before retrying."
        )
        return json.dumps(data, ensure_ascii=False)
    return result_str
